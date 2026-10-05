"""Descriptive trace facts; these never affect scores or infer a Bot's intent."""
from collections import Counter
from pathlib import Path

from runner.io import read_json

FACTS_VERSION = 2


def trace_facts(ui):
    actions, faults = Counter(), Counter()
    moves = blocked = quiet = run = longest = 0
    keys = ('grid', 'players', 'bombs', 'fault_counters')
    previous = ui['frames'][0]['state']
    for frame in ui['frames'][1:]:
        actions.update(str(a['action']) for a in frame['actions'])
        faults.update(c['fault'] for c in frame['calls'] if c['fault'])
        moves += sum(e['type'] == 'move' for e in frame['events'])
        blocked += len(frame['visual']['blocked_moves'])
        unchanged = not previous['bombs'] and not frame['state']['bombs'] and all(frame['state'][k] == previous[k] for k in keys)
        quiet += unchanged
        run = run + 1 if unchanged else 0
        longest = max(longest, run)
        previous = frame['state']
    return dict(version=FACTS_VERSION, moves=moves, blocked_moves=blocked, waits=actions['0'],
                actions=dict(sorted(actions.items())), call_faults=dict(sorted(faults.items())),
                quiet_ticks=quiet, longest_quiet_run=longest, quiet_tail_ticks=run)


def match_facts(row):
    facts = row.get('facts', {})
    if facts.get('version') == FACTS_VERSION:
        return facts
    # Older indexes retain a verified projection. Derive facts without writing
    # during a read request or changing archived reports / Replay evidence.
    path = Path(row.get('projection') or '')
    if not path.is_file():
        return None
    ui = read_json(path)
    if ui.get('source_sha256') != row.get('source_sha256') or not ui.get('verified'):
        raise ValueError('Legacy analysis projection differs from verified match')
    return trace_facts(ui)


def summarize(rows):
    valid = [m for m in rows if m.get('status') == 'completed' and m.get('verified')
             and (m.get('result') or {}).get('valid')]
    draws = [m for m in valid if all(p['placement_score'] == .5 for p in m['result']['players'])]
    stats = Counter()
    for match in valid:
        for player in match['result']['stats']:
            for key, value in player.items():
                stats[key] = max(stats[key], value) if key == 'max_tick_fuel' else stats[key] + value
    facts = {m['id']: match_facts(m) for m in valid}
    available = [f for f in facts.values() if f is not None]
    actions, faults = Counter(), Counter()
    for fact in available:
        actions.update(fact['actions']); faults.update(fact['call_faults'])
    examples = sorted([m for m in draws if facts[m['id']] is not None and facts[m['id']]['quiet_tail_ticks'] > 0],
                      key=lambda m: (-facts[m['id']]['quiet_tail_ticks'], m['id']))[:3]
    return dict(matches=len(valid), excluded_matches=len(rows)-len(valid), scope='verified_completed_matches',
                reasons=dict(sorted(Counter(m['result']['reason'] for m in valid).items())),
                draws=len(draws), draw_reasons=dict(sorted(Counter(m['result']['reason'] for m in draws).items())),
                stats=dict(sorted(stats.items())), bombs_placed=stats['bombs_placed'],
                moves=sum(f['moves'] for f in available), blocked_moves=sum(f['blocked_moves'] for f in available),
                waits=sum(f['waits'] for f in available), actions=dict(sorted(actions.items())),
                call_faults=dict(sorted(faults.items())), facts_matches=len(available),
                facts_unavailable=[m['id'] for m in valid if facts[m['id']] is None],
                quiet_ticks=sum(f['quiet_ticks'] for f in available),
                longest_quiet_run=max((f['longest_quiet_run'] for f in available), default=0),
                draw_patterns=dict(
                    no_bomb=sum(not sum(s['bombs_placed'] for s in m['result']['stats']) for m in draws),
                    no_successful_move=sum(facts[m['id']]['moves'] == 0 for m in draws if facts[m['id']] is not None),
                    with_fault=sum(any(s['action_faults'] or s['runtime_eliminations'] or s['initialization_failures']
                                       for s in m['result']['stats']) for m in draws),
                    with_explosion_death=sum(any(s['explosion_deaths'] for s in m['result']['stats']) for m in draws)),
                quiet_draw_examples=[dict(id=m['id'], ticks=m['result']['ticks'],
                                         quiet_tail_ticks=facts[m['id']]['quiet_tail_ticks'],
                                         entrants=[e['id'] for e in m['entrants']],
                                         case_index=(m.get('case') or {}).get('case_index'),
                                         swapped=(m.get('case') or {}).get('swapped'),
                                         source_sha256=m['source_sha256']) for m in examples],
                definitions=dict(quiet_tick='No active bomb before/after and no change to grid, players or fault counters; clock/call metadata excluded.',
                                 actions='Normalized engine actions, including WAIT fallback; not Bot intent.',
                                 examples='At most three draws with a positive quiet tail, sorted descending by tail then match ID; not representative sampling.',
                                 faults='Fault co-occurrence is not causal attribution.',
                                 missing_facts='Action/quiet totals cover facts_matches only; unavailable traces are explicit.'))
