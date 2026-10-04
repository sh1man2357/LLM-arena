from dataclasses import asdict, dataclass, field
import hashlib
import json

FLOOR, HARD_WALL, SOFT_WALL = range(3)
WAIT, UP, RIGHT, DOWN, LEFT, BOMB = range(6)
DIRECTIONS = {UP: (0, -1), RIGHT: (1, 0), DOWN: (0, 1), LEFT: (-1, 0)}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Rules:
    max_ticks: int = 500
    bomb_fuse_ticks: int = 4
    bomb_capacity: int = 1
    blast_range: int = 3
    consecutive_fault_limit: int = 3
    total_fault_limit: int = 20

    def __post_init__(self):
        for value in asdict(self).values():
            if type(value) is not int or value <= 0:
                raise ValueError("Rules require positive integer parameters")
        if self.bomb_capacity != 1:
            raise ValueError("Protocol v1 supports capacity 1 only")


@dataclass
class Player:
    id: int
    x: int
    y: int
    alive: bool = True
    death_tick: int | None = None


@dataclass
class Bomb:
    id: int
    owner_id: int
    x: int
    y: int
    explode_at_tick: int
    range: int


@dataclass
class World:
    width: int
    height: int
    grid: list[int]
    players: list[Player]
    rules: Rules = field(default_factory=Rules)
    tick: int = 0
    bombs: list[Bomb] = field(default_factory=list)
    next_bomb_id: int = 0
    fault_counters: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if not (1 <= self.width <= 31 and 1 <= self.height <= 31):
            raise ValueError("Map dimensions must be in 1..31")
        if len(self.grid) != self.width * self.height or any(v not in (0, 1, 2) for v in self.grid):
            raise ValueError("Invalid grid")
        if not 2 <= len(self.players) <= 8:
            raise ValueError("Expected 2..8 players")
        if [p.id for p in self.players] != list(range(len(self.players))):
            raise ValueError("Player IDs must equal consecutive spawn slots")
        positions = [(p.x, p.y) for p in self.players if p.alive]
        if len(set(positions)) != len(positions):
            raise ValueError("Duplicate living player positions")
        for p in self.players:
            if not self.inside(p.x, p.y) or self.cell(p.x, p.y) != FLOOR:
                raise ValueError("Player position must be floor")
        if not self.fault_counters:
            self.fault_counters = [dict(id=p.id, consecutive=0, total=0) for p in self.players]

    def inside(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def cell(self, x, y):
        return self.grid[y * self.width + x]

    def state(self):
        # This order is the documented state-hash serialization contract.
        return dict(tick=self.tick, grid=self.grid.copy(),
                    players=[asdict(p) for p in sorted(self.players, key=lambda p: p.id)],
                    bombs=[asdict(b) for b in sorted(self.bombs, key=lambda b: b.id)],
                    next_bomb_id=self.next_bomb_id,
                    fault_counters=[c.copy() for c in sorted(self.fault_counters, key=lambda c: c["id"])])

    def state_hash(self):
        return digest(self.state())

    @classmethod
    def from_state(cls, width, height, rules, state):
        return cls(width, height, list(state["grid"]), [Player(**p) for p in state["players"]],
                   rules, state["tick"], [Bomb(**b) for b in state["bombs"]],
                   state["next_bomb_id"], [c.copy() for c in state["fault_counters"]])

    def end_reason(self):
        count = sum(p.alive for p in self.players)
        if count == 0:
            return "all_eliminated"
        if count == 1:
            return "last_survivor"
        if self.tick >= self.rules.max_ticks:
            return "tick_limit"
        return None

    def standings(self):
        def rank(p):
            return self.rules.max_ticks + 1 if p.alive else p.death_tick
        groups = []
        for value in sorted({rank(p) for p in self.players}, reverse=True):
            groups.append([p.id for p in self.players if rank(p) == value])
        scores = []
        for p in self.players:
            wins = sum(1 if rank(p) > rank(q) else 0.5 if rank(p) == rank(q) else 0
                       for q in self.players if q.id != p.id)
            scores.append(dict(id=p.id, alive=p.alive, death_tick=p.death_tick,
                               placement_score=wins / (len(self.players) - 1)))
        return groups, scores
