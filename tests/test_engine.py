import unittest
from engine.model import *
from engine.rules import step, explode
from engine.maps import XorShift32, generate, validate, spawn_slots


def arena(positions, width=9, height=7, **rule_args):
    grid = [HARD_WALL if x in (0, width-1) or y in (0, height-1) else FLOOR
            for y in range(height) for x in range(width)]
    return World(width, height, grid, [Player(i, *pos) for i, pos in enumerate(positions)], Rules(**rule_args))


def act(world, *actions):
    return step(world, {p.id: dict(raw_action=actions[p.id], fault=None)
                        for p in world.players if p.alive})


class MovementTests(unittest.TestCase):
    def test_contention_swap_chain_cycle(self):
        w = arena([(1, 1), (3, 1)])
        act(w, RIGHT, LEFT)
        self.assertEqual([(p.x, p.y) for p in w.players], [(1, 1), (3, 1)])
        w = arena([(1, 1), (2, 1)])
        act(w, RIGHT, LEFT)
        self.assertEqual([p.x for p in w.players], [1, 2])
        act(w, RIGHT, RIGHT)
        self.assertEqual([p.x for p in w.players], [2, 3])
        w = arena([(1, 1), (2, 1), (2, 2), (1, 2)])
        act(w, RIGHT, DOWN, LEFT, UP)
        self.assertEqual([(p.x, p.y) for p in w.players], [(1, 1), (2, 1), (2, 2), (1, 2)])

    def test_blocked_chain_and_wall(self):
        w = arena([(1, 1), (2, 1), (3, 1)])
        act(w, RIGHT, RIGHT, WAIT)
        self.assertEqual([p.x for p in w.players], [1, 2, 3])
        act(w, UP, WAIT, WAIT)
        self.assertEqual(w.players[0].y, 1)

    def test_bomb_exit_no_reentry(self):
        w = arena([(1, 1), (7, 5)])
        act(w, BOMB, WAIT)
        act(w, RIGHT, WAIT)
        act(w, LEFT, WAIT)
        self.assertEqual(w.players[0].x, 2)
        self.assertEqual(w.next_bomb_id, 1)

    def test_fault_releases_occupied_cell(self):
        w = arena([(1, 1), (2, 1)])
        step(w, {0: dict(raw_action=RIGHT, fault=None), 1: dict(raw_action=None, fault="trap")})
        self.assertEqual(w.players[0].x, 2)
        self.assertFalse(w.players[1].alive)

    def test_call_order_independent(self):
        w = arena([(1, 1), (2, 1)])
        v = World.from_state(w.width, w.height, w.rules, w.state())
        calls = {0: dict(raw_action=RIGHT), 1: dict(raw_action=RIGHT)}
        self.assertEqual(step(w, calls), step(v, dict(reversed(list(calls.items())))))
        self.assertEqual(w.state_hash(), v.state_hash())


class ExplosionTests(unittest.TestCase):
    def test_fuse_and_escape_at_deadline(self):
        w = arena([(3, 3), (7, 5)])
        act(w, BOMB, WAIT)
        self.assertEqual(w.bombs[0].explode_at_tick, 4)
        for _ in range(3):
            act(w, WAIT, WAIT)
        self.assertTrue(w.players[0].alive)
        # A moves off the row/column on the exact deadline.
        w.players[0].x = 4
        act(w, UP, WAIT)
        self.assertTrue(w.players[0].alive)
        self.assertFalse(w.bombs)

    def test_new_bomb_chain_and_dead_owner(self):
        w = arena([(3, 3), (7, 5)])
        w.bombs = [Bomb(0, 1, 1, 3, 0, 3)]
        w.next_bomb_id = 1
        _, events = act(w, BOMB, WAIT)
        self.assertEqual([e["bomb"] for e in events if e["type"] == "explode"], [0, 1])
        self.assertFalse(w.players[0].alive)
        w = arena([(1, 1), (7, 5), (7, 1)])
        w.bombs = [Bomb(0, 0, 4, 5, 1, 3)]
        step(w, {0: dict(fault="trap"), 1: dict(raw_action=WAIT), 2: dict(raw_action=WAIT)})
        self.assertEqual(len(w.bombs), 1)
        act(w, WAIT, WAIT, WAIT)
        self.assertFalse(w.players[1].alive)
        self.assertTrue(w.players[2].alive)
        self.assertFalse(w.bombs)

    def test_hard_wall_and_no_lingering_flames(self):
        w = arena([(1, 1), (7, 5)])
        w.grid[3*w.width+3] = HARD_WALL
        w.grid[2*w.width+2] = SOFT_WALL
        w.bombs = [Bomb(0, 0, 2, 3, 0, 3)]
        coverage = explode(w, [0])[2]
        self.assertNotIn((3, 3), coverage)
        self.assertNotIn((4, 3), coverage)
        self.assertNotIn((2, 1), coverage)
        act(w, WAIT, WAIT)
        self.assertEqual(w.cell(3, 3), HARD_WALL)
        self.assertEqual(w.cell(2, 2), FLOOR)
        act(w, RIGHT, WAIT)
        act(w, DOWN, WAIT)
        self.assertTrue(w.players[0].alive)
        self.assertEqual((w.players[0].x, w.players[0].y), (2, 2))

    def test_soft_wall_snapshot_and_root_order(self):
        w = arena([(1, 1), (7, 5)])
        w.grid[3*w.width+4] = SOFT_WALL
        w.bombs = [Bomb(0, 0, 2, 3, 0, 5), Bomb(1, 1, 6, 3, 0, 5)]
        first = explode(w, [0, 1])
        self.assertEqual(first, explode(w, [1, 0]))
        self.assertEqual(first[1], {(4, 3)})
        self.assertEqual(first[2][(3, 3)], {0})
        self.assertEqual(first[2][(5, 3)], {1})
        _, events = act(w, WAIT, WAIT)
        self.assertEqual(w.cell(4, 3), FLOOR)

    def test_bomb_blocks_ray_but_chain_propagates_own_range(self):
        w = arena([(1, 1), (7, 5)])
        w.bombs = [Bomb(0, 0, 1, 3, 0, 6), Bomb(1, 1, 3, 3, 9, 1)]
        det, _, coverage = explode(w, [0])
        self.assertEqual(det, {0, 1})
        self.assertNotIn((5, 3), coverage)
        self.assertEqual(coverage[4, 3], {1})

    def test_all_eliminated_and_mixed_owners(self):
        w = arena([(3, 3), (5, 3)])
        w.bombs = [Bomb(0, 0, 2, 3, 0, 4), Bomb(1, 1, 6, 3, 0, 4)]
        _, events = act(w, WAIT, WAIT)
        self.assertEqual(w.end_reason(), "all_eliminated")
        self.assertEqual([s["placement_score"] for s in w.standings()[1]], [.5, .5])
        self.assertTrue(all(e["owners"] == [0, 1] for e in events if e["type"] == "death"))


class FaultAndRankingTests(unittest.TestCase):
    def test_consecutive_total_reset(self):
        w = arena([(1, 1), (7, 5)], total_fault_limit=4)
        act(w, 99, WAIT)
        act(w, WAIT, WAIT)
        self.assertEqual(w.fault_counters[0], dict(id=0, consecutive=0, total=1))
        for _ in range(3):
            act(w, 99, WAIT)
        self.assertFalse(w.players[0].alive)
        self.assertEqual(w.players[0].death_tick, 4)
        self.assertEqual(w.end_reason(), "last_survivor")

    def test_total_fault_limit(self):
        w = arena([(1, 1), (7, 5)], total_fault_limit=2)
        act(w, 99, WAIT)
        act(w, WAIT, WAIT)
        act(w, 99, WAIT)
        self.assertFalse(w.players[0].alive)

    def test_limit_init_and_multiplayer_ties(self):
        w = arena([(1, 1), (7, 5)], max_ticks=1)
        act(w, WAIT, WAIT)
        self.assertEqual(w.end_reason(), "tick_limit")
        self.assertEqual(w.standings()[0], [[0, 1]])
        w = arena([(1, 1), (2, 1), (3, 1), (4, 1), (5, 1)])
        for p, death in zip(w.players, [None, None, 3, 2, -1]):
            p.alive, p.death_tick = death is None, death
        self.assertEqual([s["placement_score"] for s in w.standings()[1]], [.875, .875, .5, .25, 0])


class MapTests(unittest.TestCase):
    def test_multiplayer_maps_clear_every_spawn_and_preserve_symmetry(self):
        for count in range(2, 9):
            for seed in range(20):
                with self.subTest(count=count, seed=seed):
                    m = generate(seed, count)
                    self.assertEqual(m, generate(seed, count))
                    self.assertTrue(validate(m['grid'], count))
                    self.assertEqual(m['grid'], m['grid'][::-1])
                    self.assertEqual(m['spawns'], [list(p) for p in spawn_slots(count)])
                    self.assertEqual(len(set(map(tuple, m['spawns']))), count)
                    World(13, 11, m['grid'], [Player(i, *p) for i, p in enumerate(m['spawns'])])
                    for sx, sy in m['spawns']:
                        for y in range(11):
                            for x in range(13):
                                if abs(x - sx) + abs(y - sy) <= 2 and m['grid'][y * 13 + x] != HARD_WALL:
                                    self.assertEqual(m['grid'][y * 13 + x], FLOOR)

    def test_invalid_player_counts(self):
        for count in (0, 1, 9, 2.0, True):
            with self.assertRaises(ValueError):
                generate(1, count)

    def test_frozen_map_and_state_vectors(self):
        import json
        from pathlib import Path
        fixture = json.loads((Path(__file__).parent / "fixtures/vectors.json").read_text(encoding="utf-8"))
        m = generate(1)
        self.assertEqual(m, fixture["map_seed_1"])
        w = World(13, 11, m["grid"], [Player(i, *p) for i, p in enumerate(m["spawns"])])
        self.assertEqual(w.state_hash(), fixture["initial_state_sha256"])

    def test_rng_vector(self):
        rng = XorShift32(1)
        self.assertEqual([rng.next() for _ in range(5)], [270369, 67634689, 2647435461, 307599695, 2398689233])

    def test_maps_legal_reproducible(self):
        for seed in range(100):
            m = generate(seed)
            self.assertTrue(validate(m["grid"]))
            self.assertEqual(m, generate(seed))
        self.assertEqual(generate(0)["grid"], generate(0x6D2B79F5)["grid"])


if __name__ == "__main__":
    unittest.main()
