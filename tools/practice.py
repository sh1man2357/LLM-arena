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
from runner.rating import strengths

BASELINES = ("baseline",)


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


def practice(source, wasm, output, opponents, maps, players=2, game_id="bomberman", opening_mode="library"):
    if game_id == "gomoku":
        from tools.gomoku_practice import practice as gomoku_practice
        return gomoku_practice(source, wasm, output, opponents, maps, players, opening_mode)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Output directory already exists; choose a new practice directory")
    if not 1 <= maps <= 10 or not opponents or any(name not in BASELINES for name in opponents):
        raise ValueError("Use 1..10 public maps and known baseline opponents")
    if type(players) is not int or not 2 <= players <= 8:
        raise ValueError("Use 2..8 players, each fighting independently")
    cases = read_json(ROOT / "configs/public-dev.json")[:maps]
    if any(len(case['bot_seeds']) < players for case in cases):
        raise ValueError("Public cases require one seed per player")
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
            scores = []
            for index, case in enumerate(cases):
                base = [dict(id="candidate", wasm=str(candidate))] + [dict(id=name, wasm=str(baseline)) for _ in range(players - 1)]
                base_seeds = [int(s, 16) for s in case["bot_seeds"][:players]]
                for slot in range(players):
                    # Seeds follow their independent instances through every spawn slot.
                    entrants = base[-slot:] + base[:-slot] if slot else base
                    seeds = base_seeds[-slot:] + base_seeds[:-slot] if slot else base_seeds
                    suffix = ('swap' if slot else 'first') if players == 2 else f'slot-{slot}'
                    mid = f"{name}-{index:02d}-{suffix}"
                    result, records = run_match(backend, entrants, case["map_seed"], seeds, mid,
                                                replay_path=output / "replays" / f"{mid}.jsonl")
                    verify_world(records)
                    scores.append(result["players"][slot]["placement_score"])
                    top = result['groups'][0]
                    wins += slot in top and len(top) == 1
                    draws += slot in top and len(top) > 1
                    losses += slot not in top
            count = wins + draws + losses
            rating = strengths([('candidate',name,score,1) for score in scores], name)['candidate']
            rows.append(dict(opponent=name, matches=count, wins=wins, draws=draws, losses=losses,
                             mean_placement=statistics.mean(scores), rating=rating))
            print(f"{name}: W/L/D {wins}/{losses}/{draws}", flush=True)
    summary = dict(status="complete", purpose="public_development_only", maps=len(cases),
                   player_count=players, game_mode='free_for_all',
                   matches=sum(r["matches"] for r in rows), mean_placement=statistics.mean(r["mean_placement"] for r in rows),
                   rating=rows[0]['rating'], reference_rating=0, rating_method='anchored_bradley_terry',
                   source_sha256=sha_file(source) if source else None, wasm_sha256=sha_file(candidate), opponents=rows)
    write_json(output / "summary.json", summary)
    lines = ["# Public practice", "", "Public development results, separate from the local application leaderboard.", "",
             f"{players} players, free for all. One candidate and {players - 1} independent copies of each baseline, rotating through every spawn slot.", "",
             "Wins: sole first; draws: tied first; losses: all other placements. Mean score uses normalized placement points.", "",
             "| Opponent | W / L / D | Mean score | Strength (reference = 0) |", "| --- | --- | --- | --- |"]
    lines += [f"| {r['opponent']} | {r['wins']} / {r['losses']} / {r['draws']} | {r['mean_placement']:.3f} | {r['rating']:+.2f} |" for r in rows]
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--source"); inputs.add_argument("--wasm")
    parser.add_argument("--output", required=True)
    parser.add_argument("--game", choices=("bomberman", "gomoku"), default="bomberman")
    parser.add_argument("--opponent", choices=("baseline",), default="baseline")
    parser.add_argument("--maps", type=int, choices=range(1, 13))
    parser.add_argument("--opening-mode", choices=("empty", "library"), default="library")
    parser.add_argument("--players", type=int, choices=range(2, 9), default=2)
    args = parser.parse_args()
    try:
        result = practice(args.source, args.wasm, args.output,
                          (args.opponent,), args.maps or (12 if args.game == "gomoku" else 10),
                          args.players, args.game, args.opening_mode)
        print(f"Complete: {result['matches']} matches. Read {Path(args.output).resolve() / 'summary.md'}")
    except (ValueError, OSError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
