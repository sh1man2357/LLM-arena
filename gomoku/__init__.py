"""Free-style Gomoku: deterministic rules, protocol and recordings."""

GAME_ID = "gomoku"
SIZE = 15
MOVE_FUEL = 20_000_000
INIT_FUEL = 10_000_000
RESIGN = SIZE * SIZE
RULES = dict(size=SIZE, win_length=5, overline_wins=True, forbidden_moves=False)
