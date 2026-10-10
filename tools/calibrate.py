"""Exercise fixed public extreme observations without changing the fuel contract."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.maps import generate
from engine.model import Player, Bomb, Rules, World, SOFT_WALL, FLOOR
from runner.io import read_json, write_json, sha_file
from runtime.wasm import Backend, INIT_FUEL, TICK_FUEL
from runtime.protocol import encode


def scenarios():
    m = generate(1)
    players = [Player(i, *p) for i, p in enumerate(m["spawns"])]
    yield "initial-map", World(13, 11, m["grid"], players)
    cleared = [FLOOR if v == SOFT_WALL else v for v in m["grid"]]
    yield "all-soft-walls-cleared", World(13, 11, cleared, players)
    for fuse in range(5):
        w = World(13, 11, cleared, players)
        w.bombs = [Bomb(0, 0, 1, 1, fuse, 3), Bomb(1, 1, 11, 9, 4, 3)]
        w.next_bomb_id = 2
        yield f"two-bombs-fuse-{fuse}", w
    positions = [(1, 1), (11, 9), (1, 9), (11, 1), (5, 1), (7, 9), (3, 5), (9, 5)]
    w = World(13, 11, cleared, [Player(i, *p) for i, p in enumerate(positions)])
    w.bombs = [Bomb(i, i, *p, i % 5, 3) for i, p in enumerate(positions)]
    w.next_bomb_id = 8
    yield "protocol-stress-eight-players", w


def main():
    p = argparse.ArgumentParser(); p.add_argument("--entrants", required=True); p.add_argument("--output", required=True)
    args = p.parse_args(); rows = []
    with Backend() as backend:
        for entrant in read_json(args.entrants):
            module = backend.load(entrant["wasm"])
            for name, world in scenarios():
                for slot in range(len(world.players)):
                    instance = backend.instance(module, 0xfedcba9876543210)
                    try:
                        call = instance.call(encode(world, slot))
                        rows.append(dict(entrant=entrant["id"], wasm_sha256=sha_file(entrant["wasm"]),
                                         scenario=name, slot=slot, init_fuel_used=instance.init_fuel_used, **call))
                    finally: instance.close()
    failures = [r for r in rows if r["fault"]]
    maximum = max(r["fuel_used"] for r in rows)
    proof = dict(status="passed" if not failures else "failed", init_fuel=INIT_FUEL, tick_fuel=TICK_FUEL,
                 observations=len(rows), max_fuel_used=maximum, max_budget_fraction=maximum/TICK_FUEL,
                 failures=failures, rows=rows)
    write_json(args.output, proof)
    print({k: v for k, v in proof.items() if k not in ("rows", "failures")})
    if failures: raise SystemExit(1)


if __name__ == "__main__": main()
