from collections import defaultdict
import random
from statistics import mean
from engine.model import digest
from runner.io import read_json, write_json, sha_file
from replay.verify import read, verify_world

BOOTSTRAP_SEED, BOOTSTRAP_SAMPLES = 20261005, 2000


def percentile(values, quantile):
    values = sorted(values)
    position = (len(values)-1)*quantile
    lo = int(position); hi = min(lo+1, len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(position-lo)


def interval(values):
    if len(values) < 10:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    samples = [mean(rng.choices(values, k=len(values))) for _ in range(BOOTSTRAP_SAMPLES)]
    return [percentile(samples, .025), percentile(samples, .975)]


def aggregate(manifest, plan, results):
    if len({p["match_id"] for p in plan}) != len(plan) or digest(plan) != manifest["schedule_sha256"]:
        raise ValueError("Invalid or duplicate frozen schedule")
    expected = {p["match_id"]: p for p in plan}
    if len({r["match_id"] for r in results}) != len(results):
        raise ValueError("Duplicate result match_id")
    if any(r["match_id"] not in expected for r in results):
        raise ValueError("Result not in frozen schedule")
    missing = sorted(set(expected)-{r["match_id"] for r in results})
    failed = sorted(r["match_id"] for r in results if not r.get("valid"))
    if missing or failed:
        return dict(status="incomplete", missing=missing, infrastructure_failures=failed,
                    expected_matches=len(plan), supplied_matches=len(results), pairs=[], entrants=[])
    pairs = defaultdict(list)
    for r in results:
        item = expected[r["match_id"]]
        if len(r["players"]) != 2 or [p["id"] for p in r["players"]] != [0, 1]:
            raise ValueError("Invalid player result slots")
        if sum(p["placement_score"] for p in r["players"]) != 1:
            raise ValueError("Invalid dual-player score")
        pairs[tuple(item["pair"])].append((item, r))
    summaries, entrants = [], defaultdict(list)
    for pair, matches in sorted(pairs.items()):
        for target in pair:
            scores, case_scores = [], defaultdict(list)
            wins = losses = draws = 0
            slots = [[], []]
            stats = defaultdict(int)
            lengths = []
            for item, r in matches:
                slot = item["entrants"].index(target)
                score = r["players"][slot]["placement_score"]
                if score not in (0, .5, 1):
                    raise ValueError("Invalid 1v1 score")
                scores.append(score); case_scores[item["case_index"]].append(score); slots[slot].append(score)
                wins += score == 1; losses += score == 0; draws += score == .5
                lengths.append(r["ticks"])
                for key, value in r["stats"][slot].items():
                    if key == "max_tick_fuel":
                        stats[key] = max(stats[key], value)
                    else:
                        stats[key] += value
            if any(len(v) != 2 for v in case_scores.values()):
                raise ValueError("Each case needs both spawn permutations")
            values = [mean(v) for _, v in sorted(case_scores.items())]
            row = dict(entrant=target, opponent=next(p for p in pair if p != target), matches=len(scores),
                       wins=wins, losses=losses, draws=draws, mean_placement=mean(scores),
                       ci95=interval(values), mean_ticks=mean(lengths),
                       spawn_mean=[mean(s) for s in slots], case_means=values, stats=dict(stats),
                       rates=dict(action_faults_per_call=stats["action_faults"]/stats["calls"] if stats["calls"] else 0,
                                  fuel_exhaustions_per_call=stats["fuel_exhaustions"]/stats["calls"] if stats["calls"] else 0,
                                  runtime_eliminations_per_match=stats["runtime_eliminations"]/len(scores),
                                  initialization_failures_per_match=stats["initialization_failures"]/len(scores)))
            summaries.append(row); entrants[target].append(row["mean_placement"])
    return dict(status="complete", expected_matches=len(plan), valid_matches=len(results),
                bootstrap=dict(seed=BOOTSTRAP_SEED, samples=BOOTSTRAP_SAMPLES, unit="map_swap_pair",
                               quantiles=[.025, .975], interpolation="linear (n-1)*q", min_cases=10),
                pairs=summaries, entrants=[dict(id=key, opponent_count=len(values), mean_placement=mean(values))
                                          for key, values in sorted(entrants.items())],
                limitations=["Intervals measure map-case variation, not model code-generation variation.",
                             "No long-term Rating; fixed opponent pool required for comparable means."])


def generate_report(output):
    manifest, plan = read_json(output / "manifest.json"), read_json(output / "schedule.json")
    results = read(output / "results.jsonl")
    for result in results:
        if result.get("valid"):
            path = output / "replays" / f"{result['match_id']}.jsonl"
            records = read(path)
            verify_world(records)
            if dict(records[-1], replay_sha256=sha_file(path)) != result:
                raise ValueError("Report result differs from authoritative Replay")
    report = aggregate(manifest, plan, results)
    write_json(output / "report.json", report)
    lines = ["# LLM Arena v0.1 report", "", f"Status: {report['status']}", ""]
    if report["status"] == "complete":
        lines += ["| Entrant | Opponent | W / L / D | Mean placement | 95% map interval |",
                  "| --- | --- | --- | --- | --- |"]
        for row in report["pairs"]:
            lines.append(f"| {row['entrant']} | {row['opponent']} | {row['wins']} / {row['losses']} / {row['draws']} | "
                         f"{row['mean_placement']:.3f} | {row['ci95']} |")
        lines += ["", f"Valid matches: {report['valid_matches']}",
                  "", "Auxiliary rates and spawn/case breakdowns are in report.json.",
                  "", *report["limitations"]]
    else:
        lines += [f"Missing matches: {len(report['missing'])}", f"Infrastructure failures: {len(report['infrastructure_failures'])}",
                  "", "No official aggregate scores are emitted for an incomplete run."]
    (output / "report.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    return report
