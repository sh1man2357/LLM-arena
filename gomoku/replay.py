"""Reconstruct every public frame from verified rule transitions."""
import re
from gomoku import SIZE, RULES, INIT_FUEL, MOVE_FUEL
from gomoku.rules import World, opening, empty_stats, account, result as make_result


def require(condition, message):
    if not condition:
        raise ValueError(message)


def project(records, *, partial=False, source_hash=None):
    require(1 <= len(records) <= 227, "Invalid Gomoku recording length")
    h = records[0]
    require(h.get("type") == "header" and h.get("game_id") == "gomoku" and h.get("schema_version") == 1,
            "Invalid Gomoku header")
    require(h["rules"] == RULES and h["budget"] == dict(init_fuel=INIT_FUEL, tick_fuel=MOVE_FUEL), "Unsupported Gomoku contract")
    require(isinstance(h["match_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", h["match_id"]), "Invalid match identity")
    require(len(h["entrants"]) == len(h["bot_seeds"]) == 2, "Expected two entrants/seeds")
    for i, e in enumerate(h["entrants"]):
        require(e.get("slot") == i and isinstance(e.get("id"), str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", e["id"])
                and isinstance(e.get("wasm_sha256"), str) and re.fullmatch(r"[a-f0-9]{64}", e["wasm_sha256"]), "Invalid entrant")
        require(isinstance(h["bot_seeds"][i], str) and re.fullmatch(r"[a-f0-9]{16}", h["bot_seeds"][i]), "Invalid Bot seed")
    terminal = records[-1].get("type") == "result"
    outcome = records[-1] if terminal else None
    failed = bool(outcome and outcome.get("valid") is False)
    require(len(h["initialization"]) == 2 or (failed and len(h["initialization"]) <= 2), "Missing initialization")
    stats = [empty_stats(), empty_stats()]
    for i, init in enumerate(h["initialization"]):
        require(init.get("id") == i and init.get("status") in ("ok", "eliminated"), "Invalid initialization")
        if init["status"] == "ok":
            require(type(init.get("fuel_used")) is int and 0 <= init["fuel_used"] <= INIT_FUEL, "Invalid initialization fuel")
        else:
            stats[i]["initialization_failures"] = 1
    world = World(opening(h["map_seed"], h["opening_mode"]))
    require(h["map"] == dict(width=SIZE, height=SIZE, moves=world.moves), "Opening differs from generator")
    if len(h["initialization"]) == 2:
        world.initialize(h["initialization"])
    require(h["initial_state"] == world.state() and h["initial_state_hash"] == world.state_hash(), "Initial state mismatch")
    frames = [dict(seq=0, tick=None, state=world.state(), events=[], actions=[], calls=[], visual={})]
    for record in records[1:]:
        if record.get("type") == "result":
            require(record is records[-1], "Early result")
            continue
        require(record.get("type") == "tick" and record["tick"] == world.tick and record["before_hash"] == world.state_hash(), "Nonsequential Gomoku frame")
        require(len(record["calls"]) == 1, "Expected one call")
        call = record["calls"][0]
        require(type(call.get("id")) is int and call["id"] == world.turn_id and type(call.get("fuel_used")) is int
                and 0 <= call["fuel_used"] <= MOVE_FUEL, "Invalid call metadata")
        calls = {call["id"]: {k: v for k, v in call.items() if k != "id"}}
        actions, events = world.step(calls)
        account(stats, calls, events)
        require(record["actions"] == [dict(id=i, action=a) for i, a in actions.items()] and record["events"] == events
                and record["state"] == world.state() and record["after_hash"] == world.state_hash(), "Gomoku frame mismatch")
        frames.append(dict(seq=len(frames), tick=record["tick"], state=world.state(), events=events,
                           actions=record["actions"], calls=[{k: call.get(k) for k in ("id", "raw_action", "fault", "fuel_used")}], visual={}))
    verified = False
    public_result = None
    if outcome:
        require(type(outcome.get("valid")) is bool, "Invalid result validity")
        if outcome["valid"]:
            require(world.reason is not None and outcome == make_result(world, stats, h["match_id"]), "Final result mismatch")
            verified = True
        else:
            require(outcome.get("reason") == "infrastructure_failure" and outcome.get("ticks") == world.tick
                    and outcome.get("players") == [] and outcome.get("stats") == stats, "Invalid infrastructure result")
        public_result = {k: outcome.get(k) for k in ("valid", "reason", "ticks", "winner", "groups", "players", "stats", "winning_line", "final_state_hash")}
    elif not partial:
        raise ValueError("Missing Gomoku final result")
    components = {k: h["components"].get(k) for k in ("benchmark_id", "ruleset", "sdk", "runtime", "source_hash")}
    require(all(isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", v) for v in components.values())
            and re.fullmatch(r"[a-f0-9]{64}", components["source_hash"]), "Invalid components")
    return dict(schema_version=1, projection_version=1, game_id="gomoku", source_sha256=source_hash,
                match_id=h["match_id"], width=SIZE, height=SIZE,
                entrants=[{k: e[k] for k in ("id", "slot", "wasm_sha256")} for e in h["entrants"]], rules=RULES.copy(),
                budget=h["budget"], initialization=[{k: r[k] for k in ("id", "status", "fuel_used") if k in r} for r in h["initialization"]],
                verified=verified, partial=not terminal, frames=frames, result=public_result, components=components)


def verify_world(records):
    ui = project(records)
    require(ui["verified"], "Recording has no valid final result")
    return dict(status="verified", match_id=ui["match_id"], ticks=ui["result"]["ticks"], final_state_hash=ui["result"]["final_state_hash"])
