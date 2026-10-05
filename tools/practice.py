"""Compile a candidate and play frozen baselines on public development maps only."""
import argparse
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.compiler import compile_bot
from runner.io import ROOT, read_json, sha_file, write_json
from runner.report import generate_report
from runner.tournament import run_tournament, validate_cases

BASELINES = ("random", "safe", "heuristic")


def baseline_wasm(name, output):
    bundled = ROOT / f"bots/baselines/{name}.wasm"
    manifest = ROOT / "devkit-manifest.json"
    if manifest.exists():
        expected = read_json(manifest)["files"][f"bots/baselines/{name}.wasm"]["sha256"]
        if not bundled.is_file() or sha_file(bundled) != expected:
            raise ValueError(f"Bundled {name} WASM differs from the frozen devkit")
        return bundled
    # Running from the full project: compile the same public baseline sources.
    target = output / "baselines" / f"{name}.wasm"
    compile_bot(ROOT / f"bots/baselines/{name}.cpp", target)
    return target


def practice(source, wasm, output, opponents, maps):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Output directory already exists; choose a new practice directory")
    cases = validate_cases(read_json(ROOT / "configs/public-dev.json"))[:maps]
    candidate = Path(wasm).resolve() if wasm else output / "candidate.wasm"
    if source:
        # Do not create an empty workspace for missing/oversize sources.
        source = Path(source).resolve()
        if not source.is_file() or source.stat().st_size > 1024 * 1024:
            raise ValueError("Candidate source must exist and be <= 1 MiB")
    elif not candidate.is_file():
        raise ValueError("Candidate WASM does not exist")
    output.mkdir(parents=True)
    if source:
        compile_bot(source, candidate)
    rows = []
    for name in opponents:
        baseline = baseline_wasm(name, output)
        pair = output / f"vs-{name}"
        entrants = [{"id": "candidate", "wasm": str(candidate)}, {"id": name, "wasm": str(baseline)}]
        print(f"Playing {name}: {len(cases)} public maps, {len(cases) * 2} swapped matches", flush=True)
        run_tournament(entrants, cases, pair)
        report = generate_report(pair)
        if report["status"] != "complete":
            write_json(output / "summary.json", {"status": "incomplete", "failed_opponent": name})
            raise ValueError(f"Incomplete practice against {name}; inspect its report and logs")
        row = next(row for row in report["pairs"] if row["entrant"] == "candidate")
        rows.append(row)
        print(f"{name}: W/L/D {row['wins']}/{row['losses']}/{row['draws']}, mean {row['mean_placement']:.3f}", flush=True)
    summary = dict(status="complete", purpose="public_development_only", maps=len(cases),
                   matches=sum(row["matches"] for row in rows),
                   mean_placement=statistics.mean(row["mean_placement"] for row in rows),
                   source_sha256=sha_file(source) if source else None,
                   wasm_sha256=sha_file(candidate), opponents=rows)
    write_json(output / "summary.json", summary)
    lines = ["# Public practice", "", "Public development results; not a hidden evaluation.", "",
             "| Opponent | W / L / D | Mean placement |", "| --- | --- | --- |"]
    lines += [f"| {r['opponent']} | {r['wins']} / {r['losses']} / {r['draws']} | {r['mean_placement']:.3f} |" for r in rows]
    lines += ["", f"Matches: {summary['matches']}; equal-opponent mean: {summary['mean_placement']:.3f}", "",
              "Per-opponent report.json contains fault/fuel statistics; replays/ contains each trajectory."]
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--source", help="Single bot.cpp to compile with the fixed SDK")
    inputs.add_argument("--wasm", help="Already compiled candidate WASM; still requires qualification")
    parser.add_argument("--output", required=True, help="New output directory")
    parser.add_argument("--opponent", choices=("all", *BASELINES), default="all")
    parser.add_argument("--maps", type=int, choices=range(1, 11), default=10)
    args = parser.parse_args()
    opponents = BASELINES if args.opponent == "all" else (args.opponent,)
    try:
        result = practice(args.source, args.wasm, args.output, opponents, args.maps)
        print(f"Complete: {result['matches']} matches. Read {Path(args.output).resolve() / 'summary.md'}")
    except (ValueError, OSError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
