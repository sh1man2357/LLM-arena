"""Order-independent Bradley-Terry strength, with the current reference fixed at zero."""
import math
from collections import defaultdict

RATING_SCALE = 400 / math.log(10)
PRIOR = 0.1  # Gaussian shrinkage in log-odds units keeps all-win/all-loss estimates finite.


def strengths(comparisons, reference):
    """Comparisons are (a, b, a_score, weight); same-snapshot self-play gives no evidence."""
    if reference is None:
        return {}
    totals = defaultdict(lambda: [0.0, 0.0])
    for a, b, score, weight in comparisons:
        if a == b:
            continue
        if a > b:
            a, b, score = b, a, 1-score
        totals[a, b][0] += score*weight
        totals[a, b][1] += weight
    adjacency = defaultdict(list)
    for (a,b),(points,weight) in sorted(totals.items()):
        adjacency[a].append((b,points,weight))
        adjacency[b].append((a,weight-points,weight))
    connected, pending = {reference}, [reference]
    while pending:
        for opponent, _, _ in adjacency[pending.pop()]:
            if opponent not in connected:
                connected.add(opponent); pending.append(opponent)
    estimates = {identity: 0.0 for identity in connected}
    variables = sorted(connected-{reference})
    for _ in range(600):
        delta = 0.0
        for identity in variables:
            current = estimates[identity]
            gradient, curvature = -PRIOR*current, PRIOR
            for opponent, points, weight in adjacency[identity]:
                difference = max(-40, min(40, current-estimates[opponent]))
                expected = 1/(1+math.exp(-difference))
                gradient += points-weight*expected
                curvature += weight*expected*(1-expected)
            step = max(-2, min(2, gradient/curvature))
            estimates[identity] += step
            delta = max(delta, abs(step))
        if delta < 1e-9:
            break
    return {identity: round(value*RATING_SCALE, 2) or 0.0 for identity,value in estimates.items()}
