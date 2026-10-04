from collections import Counter, defaultdict, deque
from engine.model import BOMB, DIRECTIONS, FLOOR, HARD_WALL, SOFT_WALL, WAIT, Bomb


def explode(world, roots):
    """Pure explosion closure against one immutable terrain/bomb snapshot."""
    by_id = {b.id: b for b in world.bombs}
    at = {(b.x, b.y): b for b in world.bombs}
    queue = deque(sorted(roots))
    detonated, soft = set(), set()
    coverage = defaultdict(set)
    while queue:
        bid = queue.popleft()
        if bid in detonated:
            continue
        detonated.add(bid)
        b = by_id[bid]
        coverage[b.x, b.y].add(b.owner_id)
        for dx, dy in DIRECTIONS.values():
            for distance in range(1, b.range + 1):
                x, y = b.x + dx * distance, b.y + dy * distance
                if not world.inside(x, y) or world.cell(x, y) == HARD_WALL:
                    break
                coverage[x, y].add(b.owner_id)
                if world.cell(x, y) == SOFT_WALL:
                    soft.add((x, y))
                    break
                if (x, y) in at:
                    queue.append(at[x, y].id)
                    break
    return detonated, soft, coverage


def step(world, calls):
    """Mutate one tick after *all* calls have been collected; never call a Bot."""
    if world.end_reason():
        raise ValueError("Cannot step a terminal world")
    living = {p.id for p in world.players if p.alive}
    if set(calls) != living:
        raise ValueError("Calls must exactly cover living players")
    events, actions = [], {}
    for p in world.players:
        if not p.alive:
            continue
        call = calls[p.id]
        raw, fault = call.get("raw_action"), call.get("fault")
        if fault not in (None, "fuel", "invalid_action", "trap"):
            raise ValueError("Unknown runtime fault")
        if fault is None and (type(raw) is not int or raw not in range(6)):
            fault = "invalid_action"
        counters = world.fault_counters[p.id]
        actions[p.id] = WAIT if fault else raw
        if fault:
            if fault != "trap":
                counters["consecutive"] += 1
                counters["total"] += 1
            events.append(dict(type="fault", player=p.id, fault=fault))
            if (fault == "trap" or counters["consecutive"] >= world.rules.consecutive_fault_limit
                    or counters["total"] >= world.rules.total_fault_limit):
                p.alive, p.death_tick = False, world.tick
                events.append(dict(type="death", player=p.id, cause="runtime", owners=[]))
        else:
            counters["consecutive"] = 0

    occupied = {(p.x, p.y): p.id for p in world.players if p.alive}
    bombs_at = {(b.x, b.y) for b in world.bombs}
    proposals = {}
    for p in world.players:
        if not p.alive or actions[p.id] not in DIRECTIONS:
            continue
        dx, dy = DIRECTIONS[actions[p.id]]
        target = p.x + dx, p.y + dy
        if world.inside(*target) and world.cell(*target) == FLOOR and target not in bombs_at:
            proposals[p.id] = target
    counts = Counter(proposals.values())
    proposals = {pid: target for pid, target in proposals.items() if counts[target] == 1}

    def can_move(pid, visited):
        if pid not in proposals or pid in visited:
            return False
        other = occupied.get(proposals[pid])
        return other is None or can_move(other, visited | {pid})

    approved = {pid for pid in proposals if can_move(pid, set())}
    for p in world.players:
        if p.id in approved:
            origin = [p.x, p.y]
            p.x, p.y = proposals[p.id]
            events.append(dict(type="move", player=p.id, origin=origin, target=[p.x, p.y]))

    for p in world.players:
        if not p.alive or actions[p.id] != BOMB:
            continue
        if ((p.x, p.y) not in bombs_at and
                sum(b.owner_id == p.id for b in world.bombs) < world.rules.bomb_capacity):
            b = Bomb(world.next_bomb_id, p.id, p.x, p.y,
                     world.tick + world.rules.bomb_fuse_ticks, world.rules.blast_range)
            world.next_bomb_id += 1
            world.bombs.append(b)
            bombs_at.add((b.x, b.y))
            events.append(dict(type="place", bomb=b.id, owner=p.id, x=p.x, y=p.y))

    roots = [b.id for b in world.bombs if b.explode_at_tick <= world.tick]
    detonated, soft, coverage = explode(world, roots)
    for bid in sorted(detonated):
        events.append(dict(type="explode", bomb=bid))
    for p in world.players:
        if p.alive and (p.x, p.y) in coverage:
            p.alive, p.death_tick = False, world.tick
            events.append(dict(type="death", player=p.id, cause="explosion",
                               owners=sorted(coverage[p.x, p.y])))
    for x, y in sorted(soft, key=lambda pos: pos[1] * world.width + pos[0]):
        world.grid[y * world.width + x] = FLOOR
        events.append(dict(type="destroy", x=x, y=y))
    world.bombs = [b for b in world.bombs if b.id not in detonated]
    world.tick += 1
    return actions, events
