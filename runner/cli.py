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
    map_cmd.add_argument("--players", type=int, choices=range(2, 9), default=2)
    m = sub.add_parser("match"); m.add_argument("--bot", action="append", required=True, help="id=wasm_path, in spawn order")
    m.add_argument("--map-seed", type=int, default=1); m.add_argument("--bot-seed", action="append", help="16-digit hex seed, in spawn order")
    m.add_argument("--output", required=True)
    v = sub.add_parser("verify"); v.add_argument("replay"); v.add_argument("--wasm", action="append", help="WASM paths in spawn order")
    view = sub.add_parser("view"); view.add_argument("replay"); view.add_argument("--output")
    for command in (build, base, q, map_cmd, m):
        command.add_argument("--game", choices=("bomberman", "gomoku"), default="bomberman")
    for command in (map_cmd, m):
        command.add_argument("--opening-mode", choices=("empty", "library"), default="empty")
    return p


def execute(args):
    if args.command == "build":
        return compile_bot(args.source, args.output, args.game)
    if args.command == "baselines":
        folder = Path(args.output).resolve()
        entrants, checks = [], []
        with Backend() as backend:
            for name in ("baseline",):
                wasm = folder / f"{name}.wasm"
                compile_bot(ROOT / f"bots/{'gomoku' if args.game == 'gomoku' else 'baselines'}/{name}.cpp", wasm, args.game)
                entrants.append(dict(id=name, wasm=str(wasm)))
                checks.append(dict(id=name, **qualify(backend, wasm, args.game)))
        write_json(folder / "entrants.json", entrants)
        write_json(folder / "qualification.json", checks)
        return dict(entrants=str(folder / "entrants.json"), qualification=checks)
    if args.command == "qualify":
        with Backend() as backend:
            return qualify(backend, args.wasm, args.game)
    if args.command == "map":
        if args.game == "gomoku":
            from gomoku.rules import opening
            value = dict(game_id="gomoku", width=15, height=15, opening_mode=args.opening_mode,
                         map_seed=args.seed, moves=opening(args.seed, args.opening_mode))
            write_json(args.output, value)
            return dict(output=args.output, **value)
        m = generate(args.seed, args.players); write_json(args.output, m)
        return dict(map_hash=m["map_hash"], output=args.output)
    if args.command == "match":
        folder = Path(args.output).resolve()
        if folder.exists():
            raise ValueError("Choose a new output directory; existing recordings are not overwritten")
        entrants = []
        for item in args.bot:
            name, path = item.split("=", 1)
            entrants.append(dict(id=name, wasm=str(Path(path).resolve())))
        seeds = [int(s, 16) for s in args.bot_seed] if args.bot_seed else list(range(1, len(entrants) + 1))
        if not 2 <= len(entrants) <= 8 or len(seeds) != len(entrants):
            raise ValueError("Use 2..8 Bots and one Bot seed per slot")
        with Backend() as backend:
            for entrant in entrants:
                qualify(backend, entrant["wasm"], args.game)
            if args.game == "gomoku":
                from gomoku.match import run_match as gomoku_run
                if len(entrants) != 2:
                    raise ValueError("Gomoku requires exactly two Bots")
                legs = []
                for swap in (False, True):
                    label = "swap" if swap else "first"
                    result, records = gomoku_run(backend, entrants[::-1] if swap else entrants, args.map_seed,
                                                seeds[::-1] if swap else seeds, f"single-{label}",
                                                opening_mode=args.opening_mode, replay_path=folder / f"replay-{label}.jsonl")
                    if result["valid"]:
                        verify_world(records)
                    legs.append(result)
                valid = all(r["valid"] for r in legs)
                result = dict(game_id="gomoku", valid=valid, legs=legs,
                              score=[sum(r["players"][i if k == 0 else 1-i]["placement_score"] for k, r in enumerate(legs)) for i in range(2)] if valid else None)
                write_json(folder / "result.json", result)
                return result
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
