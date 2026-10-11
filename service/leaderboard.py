"""Local statistics from verified core runs; no tournament or publication model."""
from fractions import Fraction
import math


def leaderboard(bots, runs, game_id="bomberman"):
    bots = [b for b in bots if b.get("game_id", "bomberman") == game_id]
    runs = [r for r in runs if r.get("game_id", "bomberman") == game_id]
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
                         points=Fraction(0), mean_score=None, rank=None,
                         black_matches=0, black_points=0, white_matches=0, white_points=0) for b in bots}
    valid_matches = 0
    for run in runs:
        result = run.get("result") or {}
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
    ranked = [r for r in rows.values() if r["matches"]]
    def ratio(row):
        return row["points"] / row["matches"]
    ranked.sort(key=lambda r: (-ratio(r), r["name"], r["id"]))
    last, rank = None, 0
    for index, row in enumerate(ranked, 1):
        score = ratio(row)
        rank = index if score != last else rank
        row.update(rank=rank, mean_score=float(score), points=float(row["points"]))
        if game_id == "gomoku":
            for color in ("black", "white"):
                row[color + "_mean"] = row[color + "_points"] / row[color + "_matches"] if row[color + "_matches"] else None
        last = score
    return dict(items=ranked, valid_matches=valid_matches)
