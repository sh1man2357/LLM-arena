"""Public Gomoku practice with the same SDK, budgets and paired colors as the app."""
from pathlib import Path
import statistics

from runner.compiler import compile_bot
from runner.io import ROOT, read_json, sha_file, write_json
from runner.match import qualify
from gomoku.match import run_match
from replay.verify import verify_world
from runtime.wasm import Backend
from runner.rating import strengths

BASELINES = ("baseline",)


def baseline_wasm(name, output):
    key = f"bots/gomoku/{name}.wasm"
    bundled = ROOT / key
    manifest = ROOT / "devkit-manifest.json"
    if manifest.is_file():
        data = read_json(manifest)
        if data.get("game_id") != "gomoku":
            raise ValueError("Use the Gomoku development package")
        if not bundled.is_file() or sha_file(bundled) != data["files"][key]["sha256"]:
            raise ValueError(f"Bundled {name} WASM differs from the frozen devkit")
        return bundled
    target = output / "baselines" / f"{name}.wasm"
    compile_bot(ROOT / f"bots/gomoku/{name}.cpp", target, "gomoku")
    return target


def practice(source, wasm, output, opponents, maps=12, players=2, opening_mode="library"):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Output directory already exists; choose a new practice directory")
    if type(players) is not int or players != 2:
        raise ValueError("Gomoku requires two players")
    if not 1 <= maps <= 12 or not opponents or any(n not in BASELINES for n in opponents):
        raise ValueError("Use 1..12 public openings and known Gomoku opponents")
    if opening_mode not in ("empty", "library"):
        raise ValueError("Unknown opening mode")
    candidate = Path(wasm).resolve() if wasm else output / "candidate.wasm"
    if source:
        source = Path(source).resolve()
        if not source.is_file() or source.stat().st_size > 1024 * 1024:
            raise ValueError("Candidate source must exist and be <= 1 MiB")
    elif not candidate.is_file():
        raise ValueError("Candidate WASM does not exist")
    cases = read_json(ROOT / "configs/gomoku-public-dev.json")[:maps]
    output.mkdir(parents=True)
    if source:
        compile_bot(source, candidate, "gomoku")
    rows = []
    with Backend() as backend:
        qualify(backend, candidate, "gomoku")
        for name in opponents:
            baseline = baseline_wasm(name, output)
            qualify(backend, baseline, "gomoku")
            scores, black, white = [], [], []
            wins = draws = losses = 0
            for index, case in enumerate(cases):
                base = [dict(id="candidate", wasm=str(candidate)), dict(id=name, wasm=str(baseline))]
                base_seeds = [int(s, 16) for s in case["bot_seeds"]]
                for swap in (False, True):
                    slot = int(swap)
                    mid = f"{name}-{index:02d}-{'swap' if swap else 'first'}"
                    result, records = run_match(backend, base[::-1] if swap else base, case["map_seed"],
                                                base_seeds[::-1] if swap else base_seeds, mid,
                                                opening_mode=opening_mode, replay_path=output / "replays" / f"{mid}.jsonl")
                    verify_world(records)
                    score = result["players"][slot]["placement_score"]
                    scores.append(score); (white if swap else black).append(score)
                    wins += score == 1; draws += score == .5; losses += score == 0
            rating = strengths([('candidate',name,score,1) for score in scores], name)['candidate']
            rows.append(dict(opponent=name, matches=len(scores), wins=wins, draws=draws, losses=losses, rating=rating,
                             mean_placement=statistics.mean(scores), black_mean=statistics.mean(black), white_mean=statistics.mean(white)))
            print(f"{name}: W/L/D {wins}/{losses}/{draws}", flush=True)
    summary = dict(status="complete", game_id="gomoku", purpose="public_development_only", maps=len(cases),
                   player_count=2, game_mode="paired_colors", opening_mode=opening_mode,
                   matches=sum(r["matches"] for r in rows), mean_placement=statistics.mean(r["mean_placement"] for r in rows),
                   rating=rows[0]['rating'], reference_rating=0, rating_method='anchored_bradley_terry',
                   source_sha256=sha_file(source) if source else None, wasm_sha256=sha_file(candidate), opponents=rows)
    write_json(output / "summary.json", summary)
    lines = ["# Gomoku public practice", "", "Each opening uses both colors; seeds follow the Bot. These scores are separate from the application leaderboard.", "",
             "| Opponent | W / L / D | Mean | Black | White | Strength (reference = 0) |", "| --- | --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {r['opponent']} | {r['wins']} / {r['losses']} / {r['draws']} | {r['mean_placement']:.3f} | {r['black_mean']:.3f} | {r['white_mean']:.3f} | {r['rating']:+.2f} |" for r in rows]
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
