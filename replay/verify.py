import json
from pathlib import Path
from engine.model import Rules, World
from engine.maps import generate
from engine.rules import step
from runner.match import empty_stats, account, make_result, run_match, components
from runner.io import sha_file


def read(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_world(records):
    if records and records[0].get("game_id") == "gomoku":
        from gomoku.replay import verify_world as gomoku_verify
        return gomoku_verify(records)
    require(len(records) >= 2, "Replay must include header and result")
    header, result = records[0], records[-1]
    require(header.get("type") == "header" and header.get("schema_version") == 1, "Invalid Replay header")
    require(result.get("type") == "result" and result.get("valid"), "Replay has no valid final result")
    count = len(header["entrants"])
    require(2 <= count <= 8 and len(header["bot_seeds"]) == count, "Invalid Replay slot/seed count")
    require([e["slot"] for e in header["entrants"]] == list(range(count)), "Invalid Replay slots")
    require(header["map"] == generate(header["map_seed"], count), "Replay map differs from generator")
    m, state = header["map"], header["initial_state"]
    world = World.from_state(m["width"], m["height"], Rules(**header["rules"]), state)
    require(len(world.players) == count, "Replay player count differs from entrants")
    expected = World(m["width"], m["height"], m["grid"], world.players, world.rules)
    # Validate initialization transitions separately from the recorded world.
    require(len(header["initialization"]) == len(world.players), "Missing initialization records")
    stats = [empty_stats() for _ in world.players]
    for pid, (p, init) in enumerate(zip(world.players, header["initialization"])):
        require(init["id"] == pid and [p.x, p.y] == m["spawns"][pid], "Invalid spawn/initialization mapping")
        if init["status"] == "eliminated":
            require(not p.alive and p.death_tick == -1, "Invalid initialization death")
            stats[pid]["initialization_failures"] = 1
        else:
            require(init["status"] == "ok" and p.alive and p.death_tick is None, "Invalid initialization state")
    require(state["tick"] == 0 and not state["bombs"] and state["next_bomb_id"] == 0
            and state["grid"] == m["grid"] and state["fault_counters"] == expected.fault_counters,
            "Invalid initial world")
    require(world.state_hash() == header["initial_state_hash"], "Initial state hash mismatch")
    initial_end = bool(world.end_reason())
    for record in records[1:-1]:
        require(record.get("type") == "tick" and record["tick"] == world.tick, "Nonsequential Replay tick")
        require(world.state_hash() == record["before_hash"], f"Before hash mismatch at {world.tick}")
        calls = {c["id"]: {k: v for k, v in c.items() if k != "id"} for c in record["calls"]}
        require(len(calls) == len(record["calls"]), "Duplicate call ID")
        actions, events = step(world, calls)
        account(stats, calls, events)
        require(record["actions"] == [dict(id=pid, action=actions[pid]) for pid in sorted(actions)], "Action mismatch")
        require(events == record["events"], f"Event mismatch at {record['tick']}")
        require(world.state() == record["state"] and world.state_hash() == record["after_hash"],
                f"State mismatch at {record['tick']}")
    require(world.end_reason() is not None, "Replay ends before a terminal state")
    rebuilt = make_result(world, stats, header["match_id"], "initialization_end" if initial_end else None)
    require(rebuilt == result, "Final result mismatch")
    return dict(status="verified", match_id=header["match_id"], ticks=world.tick, final_state_hash=world.state_hash())


def verify_bot(backend, records, wasm_paths):
    verify_world(records)
    header = records[0]
    require(header["components"] == components(header.get("game_id", "bomberman")), "Current source/toolchain version differs from Replay")
    require(len(wasm_paths) == len(header["entrants"]), "Expected one WASM per spawn slot")
    entrants = []
    for e, path in zip(header["entrants"], wasm_paths):
        require(e["wasm_sha256"] == sha_file(path), "WASM hash mismatch")
        entrants.append(dict(id=e["id"], wasm=str(path)))
    if header.get("game_id") == "gomoku":
        from gomoku.match import run_match as gomoku_run
        _, rerun = gomoku_run(backend, entrants, header["map_seed"], [int(s, 16) for s in header["bot_seeds"]],
                             header["match_id"], opening_mode=header["opening_mode"])
        require(rerun == records, "Gomoku Bot rerun differs from recording")
        return dict(status="bot_verified", match_id=header["match_id"])
    _, rerun = run_match(backend, entrants, header["map_seed"], [int(s, 16) for s in header["bot_seeds"]],
                         header["match_id"], Rules(**header["rules"]),
                         init_fuel=header["budget"]["init_fuel"], tick_fuel=header["budget"]["tick_fuel"])
    require(rerun == records, "Bot rerun differs from recorded calls/state/result")
    return dict(status="bot_verified", match_id=header["match_id"])
