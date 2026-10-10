"""Small CLI for compiling, running and checking a single Bot match."""
import argparse
import json
from pathlib import Path
import sys

from engine.maps import generate
from runner.compiler import compile_bot
from runner.io import ROOT, write_json
from runner.match import qualify, run_match
from runtime.wasm import Backend
from replay.verify import read, verify_world, verify_bot
from replay.view import frames


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build"); build.add_argument("source"); build.add_argument("--output", required=True)
    base = sub.add_parser("baselines"); base.add_argument("--output", default="artifacts/work/baselines")
    q = sub.add_parser("qualify"); q.add_argument("wasm")
    map_cmd = sub.add_parser("map"); map_cmd.add_argument("seed", type=int); map_cmd.add_argument("--output", required=True)
    m = sub.add_parser("match"); m.add_argument("--bot", action="append", required=True, help="id=wasm_path, in spawn order")
    m.add_argument("--map-seed", type=int, default=1); m.add_argument("--bot-seed", action="append", help="16-digit hex seed, in spawn order")
    m.add_argument("--output", required=True)
    v = sub.add_parser("verify"); v.add_argument("replay"); v.add_argument("--wasm", action="append", help="WASM paths in spawn order")
    view = sub.add_parser("view"); view.add_argument("replay"); view.add_argument("--output")
    return p


def execute(args):
    if args.command == "build":
        return compile_bot(args.source, args.output)
    if args.command == "baselines":
        folder = Path(args.output).resolve()
        entrants, checks = [], []
        with Backend() as backend:
            for name in ("random", "safe", "heuristic"):
                wasm = folder / f"{name}.wasm"
                compile_bot(ROOT / f"bots/baselines/{name}.cpp", wasm)
                entrants.append(dict(id=name, wasm=str(wasm)))
                checks.append(dict(id=name, **qualify(backend, wasm)))
        write_json(folder / "entrants.json", entrants)
        write_json(folder / "qualification.json", checks)
        return dict(entrants=str(folder / "entrants.json"), qualification=checks)
    if args.command == "qualify":
        with Backend() as backend:
            return qualify(backend, args.wasm)
    if args.command == "map":
        m = generate(args.seed); write_json(args.output, m)
        return dict(map_hash=m["map_hash"], output=args.output)
    if args.command == "match":
        folder = Path(args.output).resolve()
        if folder.exists():
            raise ValueError("Choose a new output directory; existing recordings are not overwritten")
        entrants = []
        for item in args.bot:
            name, path = item.split("=", 1)
            entrants.append(dict(id=name, wasm=str(Path(path).resolve())))
        seeds = [int(s, 16) for s in (args.bot_seed or ["0000000000000001", "0000000000000002"])]
        with Backend() as backend:
            for entrant in entrants:
                qualify(backend, entrant["wasm"])
            result, _ = run_match(backend, entrants, args.map_seed, seeds, replay_path=folder / "replay.jsonl")
        write_json(folder / "result.json", result)
        return result
    if args.command == "verify":
        records = read(args.replay)
        if args.wasm:
            with Backend() as backend:
                return verify_bot(backend, records, args.wasm)
        return verify_world(records)
    if args.command == "view":
        text = "\n".join(frames(read(args.replay)))
        if args.output:
            target = Path(args.output); target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            return dict(output=args.output)
        print(text)
        return dict(status="displayed")


def main():
    args = parser().parse_args()
    try:
        result = execute(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("valid") is False:
            raise SystemExit(1)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
