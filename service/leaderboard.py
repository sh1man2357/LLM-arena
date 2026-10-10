"""Local statistics from verified core runs; no tournament or publication model."""
from fractions import Fraction


def leaderboard(bots, runs):
    rows = {b["id"]: dict(id=b["id"], name=b["name"], matches=0, wins=0, draws=0, losses=0,
                         points=0, mean_score=None, rank=None) for b in bots}
    for run in runs:
        result = run.get("result") or {}
        if run["status"] != "completed" or not run.get("verified") or not result.get("valid"):
            continue
        entrants, players = run["entrants"], result.get("players", [])
        if len(entrants) != 2 or len(players) != 2:
            continue
        scores = {p["id"]: p["placement_score"] for p in players}
        if set(scores) != {0, 1} or any(s not in (0, .5, 1) for s in scores.values()) or sum(scores.values()) != 1:
            continue
        for entrant in entrants:
            row = rows.get(entrant["id"])
            if row is None:
                continue
            score = scores[entrant["slot"]]
            row["matches"] += 1
            row["points"] += score
            row["wins"] += score == 1
            row["draws"] += score == .5
            row["losses"] += score == 0
    ranked = [r for r in rows.values() if r["matches"]]
    def ratio(row):
        return Fraction(int(row["points"] * 2), row["matches"] * 2)
    ranked.sort(key=lambda r: (-ratio(r), r["name"], r["id"]))
    last, rank = None, 0
    for index, row in enumerate(ranked, 1):
        score = ratio(row)
        rank = index if score != last else rank
        row.update(rank=rank, mean_score=float(score))
        last = score
    return dict(items=ranked, valid_matches=sum(r["matches"] for r in ranked) // 2)
