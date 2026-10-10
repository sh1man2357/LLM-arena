"""Optional development practice on public maps using the single-match runner."""
import argparse
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.compiler import compile_bot
from runner.io import ROOT, read_json, sha_file, write_json
from runner.match import qualify, run_match
from replay.verify import verify_world
from runtime.wasm import Backend

BASELINES = ("random", "safe", "heuristic")


def baseline_wasm(name, output):
    bundled = ROOT / f"bots/baselines/{name}.wasm"
    manifest = ROOT / "devkit-manifest.json"
    if manifest.exists():
        expected = read_json(manifest)["files"][f"bots/baselines/{name}.wasm"]["sha256"]
        if not bundled.is_file() or sha_file(bundled) != expected:
            raise ValueError(f"Bundled {name} WASM differs from the frozen devkit")
        return bundled
    target = output / "baselines" / f"{name}.wasm"
    compile_bot(ROOT / f"bots/baselines/{name}.cpp", target)
    return target


def practice(source, wasm, output, opponents, maps):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Output directory already exists; choose a new practice directory")
    if not 1 <= maps <= 10 or not opponents or any(name not in BASELINES for name in opponents):
        raise ValueError("Use 1..10 public maps and known baseline opponents")
    cases = read_json(ROOT / "configs/public-dev.json")[:maps]
    candidate = Path(wasm).resolve() if wasm else output / "candidate.wasm"
    if source:
        source = Path(source).resolve()
        if not source.is_file() or source.stat().st_size > 1024 * 1024:
            raise ValueError("Candidate source must exist and be <= 1 MiB")
    elif not candidate.is_file():
        raise ValueError("Candidate WASM does not exist")
    output.mkdir(parents=True)
    if source:
        compile_bot(source, candidate)
    rows = []
    with Backend() as backend:
        qualify(backend, candidate)
        for name in opponents:
            baseline = baseline_wasm(name, output)
            qualify(backend, baseline)
            wins = draws = losses = 0
            for index, case in enumerate(cases):
                for swapped in (False, True):
                    entrants = [dict(id="candidate", wasm=str(candidate)), dict(id=name, wasm=str(baseline))]
                    seeds = [int(s, 16) for s in case["bot_seeds"]]
                    if swapped:
                        entrants.reverse(); seeds.reverse()
                    mid = f"{name}-{index:02d}-{'swap' if swapped else 'first'}"
                    result, records = run_match(backend, entrants, case["map_seed"], seeds, mid,
                                                replay_path=output / "replays" / f"{mid}.jsonl")
                    verify_world(records)
                    score = result["players"][int(swapped)]["placement_score"]
                    wins += score == 1; draws += score == .5; losses += score == 0
            count = wins + draws + losses
            rows.append(dict(opponent=name, matches=count, wins=wins, draws=draws, losses=losses,
                             mean_placement=(wins + .5 * draws) / count))
            print(f"{name}: W/L/D {wins}/{losses}/{draws}", flush=True)
    summary = dict(status="complete", purpose="public_development_only", maps=len(cases),
                   matches=sum(r["matches"] for r in rows), mean_placement=statistics.mean(r["mean_placement"] for r in rows),
                   source_sha256=sha_file(source) if source else None, wasm_sha256=sha_file(candidate), opponents=rows)
    write_json(output / "summary.json", summary)
    lines = ["# Public practice", "", "Public development results, separate from the local application leaderboard.", "",
             "| Opponent | W / L / D | Mean score |", "| --- | --- | --- |"]
    lines += [f"| {r['opponent']} | {r['wins']} / {r['losses']} / {r['draws']} | {r['mean_placement']:.3f} |" for r in rows]
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--source"); inputs.add_argument("--wasm")
    parser.add_argument("--output", required=True)
    parser.add_argument("--opponent", choices=("all", *BASELINES), default="all")
    parser.add_argument("--maps", type=int, choices=range(1, 11), default=10)
    args = parser.parse_args()
    try:
        result = practice(args.source, args.wasm, args.output,
                          BASELINES if args.opponent == "all" else (args.opponent,), args.maps)
        print(f"Complete: {result['matches']} matches. Read {Path(args.output).resolve() / 'summary.md'}")
    except (ValueError, OSError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
