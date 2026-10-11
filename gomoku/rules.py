from copy import deepcopy
from engine.model import digest
from gomoku import SIZE, RESIGN


def opening(seed=0, mode="empty"):
    if type(seed) is not int or not 0 <= seed <= 0xffffffff:
        raise ValueError("Opening seed must be uint32")
    if mode == "empty":
        return []
    if mode != "library":
        raise ValueError("Unknown opening mode")
    # Three base openings, each with four rotations, frozen with ruleset 1.
    bases = [((7, 7), (8, 7), (7, 8)), ((7, 7), (8, 8), (6, 7)),
             ((7, 7), (9, 7), (7, 6))]
    points = list(bases[seed % 3])
    for _ in range((seed // 3) % 4):
        points = [(14-y, x) for x, y in points]
    return [dict(x=x, y=y, color=1 + i % 2) for i, (x, y) in enumerate(points)]


class World:
    def __init__(self, moves=None):
        self.grid = [0] * (SIZE * SIZE)
        self.moves = []
        self.tick = 0
        self.winner = None
        self.reason = None
        self.winning_line = []
        self.fault = None
        for move in moves or []:
            if move != dict(x=move["x"], y=move["y"], color=self.turn_color):
                raise ValueError("Invalid opening move")
            x, y = move["x"], move["y"]
            if type(x) is not int or type(y) is not int or not 0 <= x < SIZE or not 0 <= y < SIZE or self.grid[y*SIZE+x]:
                raise ValueError("Invalid opening position")
            self.grid[y*SIZE+x] = move["color"]
            self.moves.append(move.copy())
            if self.line(x, y):
                raise ValueError("Opening is already terminal")

    @property
    def turn_color(self):
        return 1 + len(self.moves) % 2

    @property
    def turn_id(self):
        return self.turn_color - 1

    def line(self, x, y):
        color = self.grid[y*SIZE+x]
        if not color:
            return []
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            points = [(x, y)]
            for sign in (-1, 1):
                nx, ny = x + sign*dx, y + sign*dy
                while 0 <= nx < SIZE and 0 <= ny < SIZE and self.grid[ny*SIZE+nx] == color:
                    if sign < 0:
                        points.insert(0, (nx, ny))
                    else:
                        points.append((nx, ny))
                    nx += sign*dx; ny += sign*dy
            if len(points) >= 5:
                return [list(p) for p in points]
        return []

    def initialize(self, records):
        failed = [r["id"] for r in records if r["status"] == "eliminated"]
        if failed:
            self.reason = "initialization_failure"
            self.winner = None if len(failed) == 2 else 1-failed[0]
            self.fault = dict(players=failed, cause="initialization")

    def state(self):
        return deepcopy(dict(tick=self.tick, grid=self.grid, moves=self.moves,
                             turn_color=self.turn_color, winner=self.winner, reason=self.reason,
                             winning_line=self.winning_line, fault=self.fault))

    def state_hash(self):
        return digest(self.state())

    def step(self, calls):
        if self.reason or set(calls) != {self.turn_id}:
            raise ValueError("Expected exactly the current player's call before terminal state")
        pid = self.turn_id
        call = calls[pid]
        action, fault = call.get("raw_action"), call.get("fault")
        if fault not in (None, "fuel", "invalid_action", "trap"):
            raise ValueError("Unknown Bot fault")
        if action is not None and (type(action) is not int or not -(2**31) <= action < 2**31):
            raise ValueError("Invalid raw action")
        if not fault and (type(action) is not int or not 0 <= action <= RESIGN):
            fault = "invalid_action"
        events = []
        if fault:
            self.reason, self.winner = "bot_fault", 1-pid
            self.fault = dict(players=[pid], cause=fault)
            events.append(dict(type="fault", player=pid, cause=fault))
        elif action == RESIGN:
            self.reason, self.winner = "resignation", 1-pid
            events.append(dict(type="resign", player=pid))
        elif self.grid[action]:
            self.reason, self.winner = "illegal_move", 1-pid
            self.fault = dict(players=[pid], cause="occupied")
            events.append(dict(type="fault", player=pid, cause="occupied"))
        else:
            x, y = action % SIZE, action // SIZE
            color = self.turn_color
            self.grid[action] = color
            self.moves.append(dict(x=x, y=y, color=color))
            events.append(dict(type="stone", player=pid, color=color, x=x, y=y))
            self.winning_line = self.line(x, y)
            if self.winning_line:
                self.reason, self.winner = "five_in_row", pid
            elif len(self.moves) == SIZE*SIZE:
                self.reason = "board_full"
        self.tick += 1
        return {pid: action}, events


def empty_stats():
    return dict(calls=0, fuel_used=0, max_tick_fuel=0, stones=0, faults=0, initialization_failures=0)


def account(stats, calls, events):
    for pid, call in calls.items():
        stats[pid]["calls"] += 1
        stats[pid]["fuel_used"] += call.get("fuel_used", 0)
        stats[pid]["max_tick_fuel"] = max(stats[pid]["max_tick_fuel"], call.get("fuel_used", 0))
    for e in events:
        if e["type"] in ("stone", "fault"):
            stats[e["player"]]["stones" if e["type"] == "stone" else "faults"] += 1


def result(world, stats, match_id):
    scores = [.5, .5] if world.winner is None else [int(i == world.winner) for i in range(2)]
    groups = [[0, 1]] if world.winner is None else [[world.winner], [1-world.winner]]
    return dict(type="result", game_id="gomoku", match_id=match_id, valid=True,
                reason=world.reason, ticks=world.tick, winner=world.winner, groups=groups,
                players=[dict(id=i, color=i+1, placement_score=scores[i]) for i in range(2)],
                stats=deepcopy(stats), winning_line=deepcopy(world.winning_line), final_state_hash=world.state_hash())
