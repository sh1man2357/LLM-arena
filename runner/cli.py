import argparse
import json
from pathlib import Path
import secrets
import sys
import traceback
from engine.maps import generate
from engine.model import Player, Rules, World
from runtime.wasm import Backend, QualificationError, InitializationError
from runner.compiler import compile_bot
from runner.io import ROOT, read_json, write_json, sha_file
from runner.match import components, qualify, run_match
from runner.tournament import load_entrants, validate_cases, run_tournament
from runner.report import generate_report
from replay.verify import read, verify_world, verify_bot
from replay.view import frames


def parser():
    p = argparse.ArgumentParser(description="Deterministic C++20/WASM Bomber Arena v0.1")
    sub = p.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build"); build.add_argument("source"); build.add_argument("--output", required=True)
    baselines = sub.add_parser("baselines"); baselines.add_argument("--output", default="artifacts/work/baselines")
    q = sub.add_parser("qualify"); q.add_argument("wasm")
    seeds = sub.add_parser("seeds"); seeds.add_argument("--count", type=int, default=50); seeds.add_argument("--output", required=True)
    map_cmd = sub.add_parser("map"); map_cmd.add_argument("seed", type=int); map_cmd.add_argument("--output", required=True)
    m = sub.add_parser("match"); m.add_argument("--bot", action="append", required=True, help="entrant_id=wasm_path, in spawn order")
    m.add_argument("--map-seed", type=int, default=1); m.add_argument("--bot-seed", action="append", help="16-digit hex seed, in spawn order")
    m.add_argument("--output", required=True)
    t = sub.add_parser("tournament"); t.add_argument("--entrants", required=True); t.add_argument("--cases", required=True)
    t.add_argument("--output", required=True); t.add_argument("--resume", action="store_true"); t.add_argument("--retry-failures", action="store_true")
    rep = sub.add_parser("report"); rep.add_argument("directory")
    v = sub.add_parser("verify"); v.add_argument("replay"); v.add_argument("--wasm", action="append", help="WASM paths in spawn order")
    batch = sub.add_parser("verify-all"); batch.add_argument("directory"); batch.add_argument("--entrants", required=True)
    batch.add_argument("--rerun", action="store_true")
    view = sub.add_parser("view"); view.add_argument("replay"); view.add_argument("--output")
    return p


def execute(args):
    if args.command == "build":
        return compile_bot(args.source, args.output)
    if args.command == "baselines":
        folder = Path(args.output).resolve(); entrants = []
        for name in ("random", "safe", "heuristic"):
            compile_bot(ROOT / f"bots/baselines/{name}.cpp", folder / f"{name}.wasm")
            entrants.append(dict(id=name, wasm=str(folder / f"{name}.wasm")))
        write_json(folder / "entrants.json", entrants)
        with Backend() as backend:
            qualification = [dict(id=e["id"], **qualify(backend, e["wasm"])) for e in entrants]
        write_json(folder / "qualification.json", qualification)
        return dict(entrants=str(folder / "entrants.json"), qualification=qualification)
    if args.command == "qualify":
        with Backend() as backend:
            return qualify(backend, args.wasm)
    if args.command == "seeds":
        if not 1 <= args.count <= 10000:
            raise ValueError("Case count must be in 1..10000")
        cases, hashes = [], set()
        while len(cases) < args.count:
            seed = secrets.randbits(32); m = generate(seed)
            if m["map_hash"] in hashes:
                continue
            hashes.add(m["map_hash"])
            cases.append(dict(map_seed=seed, bot_seeds=[f"{secrets.randbits(64):016x}" for _ in range(2)]))
        write_json(args.output, cases)
        return dict(cases=len(cases), output=args.output)
    if args.command == "map":
        m = generate(args.seed); write_json(args.output, m)
        return dict(map_hash=m["map_hash"], output=args.output)
    if args.command == "match":
        entrants = []
        for item in args.bot:
            name, path = item.split("=", 1)
            entrants.append(dict(id=name, wasm=str(Path(path).resolve())))
        seeds = [int(s, 16) for s in (args.bot_seed or ["0000000000000001", "0000000000000002"])]
        folder = Path(args.output); folder.mkdir(parents=True, exist_ok=True)
        with Backend() as backend:
            for entrant in entrants:
                qualify(backend, entrant["wasm"])
            result, _ = run_match(backend, entrants, args.map_seed, seeds, replay_path=folder / "replay.jsonl")
        write_json(folder / "result.json", result)
        return result
    if args.command == "tournament":
        manifest, _, _ = run_tournament(load_entrants(args.entrants), read_json(args.cases), args.output,
                                        args.resume, args.retry_failures)
        report = generate_report(Path(args.output))
        return dict(status=report["status"], matches=manifest["expected_matches"], output=args.output)
    if args.command == "report":
        report = generate_report(Path(args.directory))
        return dict(status=report["status"], output=args.directory)
    if args.command == "verify":
        records = read(args.replay)
        if args.wasm:
            with Backend() as backend:
                return verify_bot(backend, records, args.wasm)
        return verify_world(records)
    if args.command == "verify-all":
        folder = Path(args.directory)
        report = generate_report(folder)
        if report["status"] != "complete":
            raise ValueError("Cannot verify an incomplete tournament")
        plan = read_json(folder / "schedule.json")
        manifest = read_json(folder / "manifest.json")
        entrants = load_entrants(args.entrants); lookup = {e["id"]: e["wasm"] for e in entrants}
        if [dict(id=e["id"], wasm_sha256=sha_file(e["wasm"])) for e in entrants] != manifest["entrants"]:
            raise ValueError("Entrant artifacts differ from frozen manifest")
        checks = []
        with Backend() as backend:
            for i, item in enumerate(plan):
                records = read(folder / "replays" / f"{item['match_id']}.jsonl")
                result = verify_world(records)
                if args.rerun:
                    result.update(verify_bot(backend, records, [lookup[e] for e in item["entrants"]]))
                checks.append(result)
                if (i+1) % 25 == 0:
                    print(f"Verified {i+1}/{len(plan)}", flush=True)
        proof = dict(status="verified", matches=len(checks), bot_rerun=args.rerun,
                     manifest_sha256=sha_file(folder / "manifest.json"), checks=checks)
        write_json(folder / "checks" / ("bot-rerun.json" if args.rerun else "world-replay.json"), proof)
        return dict(status="verified", matches=len(checks), bot_rerun=args.rerun)
    if args.command == "view":
        text = "\n".join(frames(read(args.replay)))
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(text, encoding="utf-8")
            return dict(output=args.output)
        print(text)
        return dict(status="displayed")


def main():
    p = parser(); args = p.parse_args()
    try:
        result = execute(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") == "incomplete" or result.get("valid") is False:
            raise SystemExit(1)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
