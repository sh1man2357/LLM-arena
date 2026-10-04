from collections import deque
from engine.model import FLOOR, HARD_WALL, SOFT_WALL, digest

WIDTH, HEIGHT = 13, 11
SPAWNS = [(1, 1), (11, 9)]


class XorShift32:
    def __init__(self, seed):
        if type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF:
            raise ValueError("Map seed must be uint32")
        self.state = seed or 0x6D2B79F5

    def next(self):
        x = self.state
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self.state = x & 0xFFFFFFFF
        return self.state


def reachable(grid, start, soft=False):
    seen, queue = {start}, deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            pos = x + dx, y + dy
            if not (0 <= pos[0] < WIDTH and 0 <= pos[1] < HEIGHT) or pos in seen:
                continue
            value = grid[pos[1] * WIDTH + pos[0]]
            if value == FLOOR or (soft and value == SOFT_WALL):
                seen.add(pos)
                queue.append(pos)
    return seen


def validate(grid):
    if len(grid) != WIDTH * HEIGHT or any(v not in (0, 1, 2) for v in grid):
        return False
    if grid != grid[::-1]:
        return False
    for y in range(HEIGHT):
        for x in range(WIDTH):
            hard = x in (0, WIDTH - 1) or y in (0, HEIGHT - 1) or (x % 2 == y % 2 == 0)
            if hard != (grid[y * WIDTH + x] == HARD_WALL):
                return False
            if not hard and any(abs(x - sx) + abs(y - sy) <= 2 for sx, sy in SPAWNS):
                if grid[y * WIDTH + x] != FLOOR:
                    return False
    regions = [reachable(grid, p) for p in SPAWNS]
    if len(regions[0]) < 5 or len(regions[0]) != len(regions[1]):
        return False
    all_floor = sum(v != HARD_WALL for v in grid)
    return len(reachable(grid, SPAWNS[0], soft=True)) == all_floor


def generate(seed):
    rng = XorShift32(seed)
    for attempt in range(1, 257):
        grid = [FLOOR] * (WIDTH * HEIGHT)
        clear = set()
        for y in range(HEIGHT):
            for x in range(WIDTH):
                i = y * WIDTH + x
                if x in (0, WIDTH - 1) or y in (0, HEIGHT - 1) or (x % 2 == y % 2 == 0):
                    grid[i] = HARD_WALL
                elif any(abs(x - sx) + abs(y - sy) <= 2 for sx, sy in SPAWNS):
                    clear.add(i)
        for i in range(len(grid)):
            partner = len(grid) - 1 - i
            if grid[i] == HARD_WALL or i in clear or i > partner:
                continue
            value = SOFT_WALL if rng.next() < 2362232012 else FLOOR
            grid[i] = grid[partner] = value
        if validate(grid):
            return dict(seed=seed, width=WIDTH, height=HEIGHT, grid=grid,
                        spawns=[list(p) for p in SPAWNS], attempts=attempt, map_hash=digest(grid))
    raise ValueError("Map generator exhausted 256 attempts")
