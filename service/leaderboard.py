"""Local statistics from verified core runs; no tournament or publication model."""
from fractions import Fraction
import math
from runner.rating import strengths
from service.bots import listed_bots


def leaderboard(bots, runs, game_id="bomberman"):
    bots = [b for b in bots if b.get("game_id", "bomberman") == game_id]
    visible = listed_bots(bots)
    reference = next((b['id'] for b in visible if b.get('baseline')), None)
    runs = [r for r in runs if r.get("game_id", "bomberman") == game_id and r.get("mode") != "human"]
    if game_id == "gomoku":
        by_id = {r["id"]: r for r in runs}
        def eligible(row):
            ids = row.get("pair_runs") or []
            if len(ids) != 2 or len(set(ids)) != 2 or row["id"] not in ids:
                return False
            legs = [by_id.get(i) for i in ids]
            if not all(r and r.get("pair_runs") == ids and r.get("pair_id") == ids[0]
                       and r.get("pair_index") == index and r["status"] == "completed" and r.get("verified")
                       and (r.get("result") or {}).get("valid") for index, r in enumerate(legs)):
                return False
            return (legs[0]["task_id"] == legs[1]["task_id"] and legs[0]["map_seed"] == legs[1]["map_seed"]
                    and legs[0].get("opening_mode") == legs[1].get("opening_mode")
                    and [e["id"] for e in legs[0]["entrants"]] == list(reversed([e["id"] for e in legs[1]["entrants"]])))
        runs = [r for r in runs if eligible(r)]
    rows = {b["id"]: dict(id=b["id"], name=b["name"], matches=0, wins=0, draws=0, losses=0,
                         points=Fraction(0), mean_score=None, rank=None, baseline=b.get('baseline',False), rating=None,
                         black_matches=0, black_points=0, white_matches=0, white_points=0) for b in bots}
    valid_matches = 0
    comparisons = []
    for run in runs:
        result = run.get("result") or {}
        if game_id == "bomberman" and result.get("scoring_version") != 2:
            continue
        if run["status"] != "completed" or not run.get("verified") or not result.get("valid"):
            continue
        entrants, players = run["entrants"], result.get("players", [])
        count = len(entrants)
        if not 2 <= count <= 8 or len(players) != count:
            continue
        scores = {p["id"]: p["placement_score"] for p in players}
        if (set(scores) != set(range(count)) or sorted(e["slot"] for e in entrants) != list(range(count))
                or any(type(s) not in (int, float) or not math.isfinite(s) or not 0 <= s <= 1
                       or not math.isclose(s * 2 * (count - 1), round(s * 2 * (count - 1)), abs_tol=1e-9)
                       for s in scores.values())
                or not math.isclose(sum(scores.values()), count / 2, abs_tol=1e-9)):
            continue
        valid_matches += 1
        for i, a in enumerate(entrants):
            for b in entrants[i+1:]:
                score_a, score_b = scores[a['slot']], scores[b['slot']]
                comparisons.append((a['id'],b['id'],1 if score_a>score_b else .5 if score_a==score_b else 0,1/(count-1)))
        top = max(scores.values())
        tied = sum(s == top for s in scores.values()) > 1
        for entrant in entrants:
            row = rows.get(entrant["id"])
            if row is None:
                continue
            score = scores[entrant["slot"]]
            row["matches"] += 1
            row["points"] += Fraction(round(score * 2 * (count - 1)), 2 * (count - 1))
            row["wins"] += score == top and not tied
            row["draws"] += score == top and tied
            row["losses"] += score != top
            if game_id == "gomoku":
                color = "black" if entrant["slot"] == 0 else "white"
                row[color + "_matches"] += 1
                row[color + "_points"] += score
    ratings = strengths(comparisons, reference)
    visible_ids = {b['id'] for b in visible}
    ranked = [r for r in rows.values() if r['id'] in visible_ids and (r["matches"] or r['id']==reference)]
    def ratio(row):
        return row["points"] / row["matches"]
    for row in ranked:
        row['rating'] = ratings.get(row['id'])
    ranked.sort(key=lambda r: (r['rating'] is None, -(r['rating'] or 0), r["name"], r["id"]))
    last, rank = None, 0
    for index, row in enumerate(ranked, 1):
        score = row['rating']
        rank = index if score != last else rank
        row.update(rank=rank if score is not None else None,
                   mean_score=float(ratio(row)) if row['matches'] else None, points=float(row["points"]))
        if game_id == "gomoku":
            for color in ("black", "white"):
                row[color + "_mean"] = row[color + "_points"] / row[color + "_matches"] if row[color + "_matches"] else None
        last = score
    return dict(items=ranked, valid_matches=valid_matches, reference_id=reference, rating_method='anchored_bradley_terry')
