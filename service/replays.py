"""Verified, seed-free spectator projection of schema-1 competition evidence."""
import hashlib
import json
import re

from engine.model import Bomb, Rules, World, digest
from engine.rules import explode, step
from replay.verify import verify_world

MAX_REPLAY_BYTES = 16 * 1024 * 1024


def decode(data):
    if len(data) > MAX_REPLAY_BYTES:
        raise ValueError("Replay exceeds 16 MiB")
    records = [json.loads(line) for line in data.decode("utf-8-sig").splitlines() if line.strip()]
    validate_shape(records)
    return records


def validate_shape(records):
    if not 1 <= len(records) <= 502:
        raise ValueError("Replay requires a header and at most 500 ticks plus result")
    h = records[0]
    if h.get("type") != "header" or h.get("schema_version") != 1:
        raise ValueError("Unsupported Replay schema; expected version 1")
    m = h["map"]
    if (m["width"], m["height"]) != (13, 11) or len(h["entrants"]) != 2:
        raise ValueError("Only 13 by 11 two-player Replay is supported")
    if h["rules"] != Rules().__dict__:
        raise ValueError("Unsupported rules; expected the frozen ruleset 1")
    if not isinstance(h.get("match_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", h["match_id"]):
        raise ValueError("Invalid Replay match identity")
    for slot, entrant in enumerate(h["entrants"]):
        if (entrant.get("slot") != slot or not isinstance(entrant.get("id"), str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", entrant["id"])
                or not isinstance(entrant.get("wasm_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", entrant["wasm_sha256"])):
            raise ValueError("Invalid Replay entrant identity/hash")
    for r in records:
        s = r.get("state") or (r.get("initial_state") if r["type"] == "header" else None)
        if s is not None and (len(s["grid"]) != 143 or len(s["players"]) != 2 or len(s["bombs"]) > 8):
            raise ValueError("Invalid Replay state dimensions")


def visual_event(previous, record, rules):
    """Derive blast geometry using the existing pure snapshot closure."""
    snapshot = World.from_state(13, 11, rules, previous)
    for e in record["events"]:
        if e["type"] == "place":
            snapshot.bombs.append(Bomb(e["bomb"], e["owner"], e["x"], e["y"],
                                       record["tick"] + rules.bomb_fuse_ticks, rules.blast_range))
    roots = [b.id for b in snapshot.bombs if b.explode_at_tick <= record["tick"]]
    detonated, _, coverage = explode(snapshot, roots)
    moved = {e["player"] for e in record["events"] if e["type"] == "move"}
    blocked = [a["id"] for a in record["actions"] if a["action"] in (1, 2, 3, 4) and a["id"] not in moved]
    return dict(coverage=[dict(x=x, y=y, owners=sorted(owners)) for (x, y), owners in sorted(coverage.items())],
                exploded_bombs=[dict(id=b.id, owner_id=b.owner_id, x=b.x, y=b.y,
                                     explode_at_tick=b.explode_at_tick, chain=b.explode_at_tick > record["tick"])
                                for b in snapshot.bombs if b.id in detonated], blocked_moves=blocked)


def project(records, *, partial=False, source_hash=None):
    validate_shape(records)
    h = records[0]
    terminal = records[-1].get("type") == "result"
    result = records[-1] if terminal else None
    verified = False
    if result and result.get("valid"):
        verify_world(records)
        verified = True
    elif not partial and not result:
        raise ValueError("Incomplete Replay; missing final result")
    rules = Rules(**h["rules"])
    previous = h["initial_state"]
    # Initial-state extensions are not part of the schema-1 world. Rebuild the
    # public state so an otherwise valid header cannot smuggle private fields.
    public_initial = World.from_state(13, 11, rules, previous).state()
    frames = [dict(seq=0, tick=None, state=public_initial, events=[], actions=[], calls=[],
                   visual=dict(coverage=[], exploded_bombs=[], blocked_moves=[]))]
    for record in records[1:]:
        if record["type"] == "result":
            continue
        if record["type"] != "tick" or record["tick"] != previous["tick"]:
            raise ValueError("Nonsequential Replay")
        world = World.from_state(13, 11, rules, previous)
        calls = {c["id"]: {k: v for k, v in c.items() if k != "id"} for c in record["calls"]}
        for call in record["calls"]:
            if (call.get("fault") not in (None, "fuel", "invalid_action", "trap")
                    or (call.get("raw_action") is not None and (type(call["raw_action"]) is not int or not -(2**31) <= call["raw_action"] < 2**31))
                    or (call.get("fuel_used") is not None and (type(call["fuel_used"]) is not int or not 0 <= call["fuel_used"] <= 2**53-1))):
                raise ValueError("Invalid public Bot call metadata")
        actions, events = step(world, calls)
        if (world.state() != record["state"] or events != record["events"] or
                record["actions"] != [dict(id=i, action=actions[i]) for i in sorted(actions)] or
                world.state_hash() != record["after_hash"]):
            raise ValueError("Recorded frame fails world verification")
        frames.append(dict(seq=len(frames), tick=record["tick"], state=record["state"],
                           events=record["events"], actions=record["actions"],
                           calls=[{k: c.get(k) for k in ("id", "raw_action", "fault", "fuel_used")} for c in record["calls"]],
                           visual=visual_event(previous, record, rules)))
        previous = record["state"]
    public_result = None
    if result:
        public_result = {k: result.get(k) for k in ("valid", "reason", "ticks", "survivors", "groups", "players", "stats", "final_state_hash")}
        if type(result.get("valid")) is not bool:
            raise ValueError("Invalid Replay result validity")
        if not result["valid"]:
            from runner.match import empty_stats
            if result.get("reason") != "infrastructure_failure" or type(result.get("ticks")) is not int or not 0 <= result["ticks"] <= 500:
                raise ValueError("Invalid infrastructure failure result")
            stats = result.get("stats", [])
            if len(stats) != 2 or any(type(s.get(k)) is not int or s[k] < 0 for s in stats for k in empty_stats()):
                raise ValueError("Invalid infrastructure statistics")
            public_result.update(players=[], groups=[], survivors=[], final_state_hash=None,
                                 stats=[{k: s[k] for k in empty_stats()} for s in stats])
    public_components = {k: h["components"].get(k) for k in ("benchmark_id", "ruleset", "map_generator", "sdk", "runtime", "source_hash")}
    if any(value is not None and (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", value))
           for value in public_components.values()):
        raise ValueError("Invalid public component identifier")
    if not re.fullmatch(r"[0-9a-f]{64}", public_components.get("source_hash") or ""):
        raise ValueError("Invalid Replay source hash")
    budget = {k: h["budget"][k] for k in ("init_fuel", "tick_fuel")}
    if any(type(value) is not int or not 0 <= value <= 2**53-1 for value in budget.values()):
        raise ValueError("Invalid Replay fuel budget")
    initialization = [{k: v for k, v in row.items() if k in ("id", "status", "fuel_used")}
                      for row in h["initialization"]]
    for i, entry in enumerate(initialization):
        if (entry.get("id") != i or entry.get("status") not in ("ok", "eliminated")
                or ("fuel_used" in entry and (type(entry["fuel_used"]) is not int or not 0 <= entry["fuel_used"] <= 2**53-1))):
            raise ValueError("Invalid initialization metadata")
    return dict(schema_version=1, projection_version=1, source_sha256=source_hash,
                match_id=h["match_id"], width=13, height=11,
                entrants=[{k: e[k] for k in ("id", "slot", "wasm_sha256")} for e in h["entrants"]], rules=h["rules"],
                budget=budget, initialization=initialization,
                verified=verified, partial=not terminal, frames=frames, result=public_result,
                components=public_components)


def from_bytes(data):
    try:
        if len(data) > MAX_REPLAY_BYTES:
            raise ValueError("Replay exceeds 16 MiB")
        try:
            value = json.loads(data.decode("utf-8-sig"))
        except json.JSONDecodeError:
            value = None  # Original JSONL contains multiple top-level records.
        if isinstance(value, dict) and "projection_version" in value:
            return from_public(value, hashlib.sha256(data).hexdigest())
        return project(decode(data), source_hash=hashlib.sha256(data).hexdigest())
    except (UnicodeDecodeError, KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError(f"Malformed Replay schema: {type(exc).__name__}") from exc


def from_public(value, file_hash):
    """Recompute seed-free world facts. Never trust uploaded verification flags."""
    from runner.match import empty_stats, account, make_result
    if (value.get("schema_version") != 1 or value.get("projection_version") not in (1, 2)
            or (value.get("width"), value.get("height")) != (13, 11)):
        raise ValueError("Unsupported public Replay schema")
    frames = value["frames"]
    if not isinstance(frames, list) or not 1 <= len(frames) <= 501 or value.get("partial") is not False:
        raise ValueError("Public Replay must include an initial frame and a complete result")
    first = frames[0]
    if first.get("seq") != 0 or first.get("tick") is not None:
        raise ValueError("Invalid public initial frame")
    rules = Rules(**value["rules"])
    world = World.from_state(13, 11, rules, first["state"])
    if (any(type(cell) is not int for cell in world.grid)
            or any(type(p.alive) is not bool or type(p.id) is not int or type(p.x) is not int or type(p.y) is not int
                   for p in world.players)):
        raise ValueError("Invalid public world value types")
    expected = World(13, 11, world.grid, world.players, rules)
    if (world.tick != 0 or world.bombs or world.next_bomb_id != 0 or world.fault_counters != expected.fault_counters
            or world.state() != first["state"] or [(p.x, p.y) for p in world.players] != [(1, 1), (11, 9)]):
        raise ValueError("Invalid public initial world")
    if len(value["initialization"]) != 2:
        raise ValueError("Missing public initialization records")
    stats = [empty_stats(), empty_stats()]
    for slot, (player, entry) in enumerate(zip(world.players, value["initialization"])):
        if entry.get("id") != slot or (entry.get("status") == "ok" and (not player.alive or player.death_tick is not None)):
            raise ValueError("Invalid public initialization state")
        if entry.get("status") == "eliminated":
            if player.alive or player.death_tick != -1:
                raise ValueError("Invalid public initialization death")
            stats[slot]["initialization_failures"] = 1
    initial_end = world.end_reason() is not None
    h = dict(type="header", schema_version=1, map=dict(width=13, height=11),
             rules=value["rules"], match_id=value["match_id"], entrants=value["entrants"],
             budget=value["budget"], components=value["components"], initialization=value["initialization"],
             initial_state=world.state())
    records = [h]
    for seq, frame in enumerate(frames[1:], 1):
        if frame.get("seq") != seq or frame.get("tick") != seq-1 or world.end_reason():
            raise ValueError("Nonsequential or post-terminal public frame")
        calls = {c["id"]: {k: v for k, v in c.items() if k != "id"} for c in frame["calls"]}
        if len(calls) != len(frame["calls"]):
            raise ValueError("Duplicate public Bot call")
        if set(calls) != {p.id for p in world.players if p.alive}:
            raise ValueError("Public calls must match the living spawn slots")
        previous = world.state()
        _, events = step(world, calls)
        account(stats, calls, events)
        record = dict(type="tick", tick=frame["tick"], before_hash=digest(previous), after_hash=digest(frame["state"]),
                      state=frame["state"], calls=frame["calls"], actions=frame["actions"], events=frame["events"])
        records.append(record)
    # The normal adapter verifies every frame and rebuilds the event geometry.
    ui = project(records, partial=True, source_hash=file_hash)
    for supplied, rebuilt in zip(frames, ui["frames"]):
        if any(supplied.get(k) != rebuilt[k] for k in ("seq", "tick", "state", "events", "actions", "calls", "visual")):
            raise ValueError("Public frame/geometry differs from reconstructed world")
    result = value["result"]
    if type(result.get("valid")) is not bool:
        raise ValueError("Invalid public result")
    if result["valid"]:
        if world.end_reason() is None:
            raise ValueError("Public Replay ends before a terminal world")
        rebuilt = make_result(world, stats, h["match_id"], "initialization_end" if initial_end else None)
        public = {k: rebuilt[k] for k in ("valid", "reason", "ticks", "survivors", "groups", "players", "stats", "final_state_hash")}
        if result != public:
            raise ValueError("Public result differs from reconstructed world")
        ui.update(result=public, verified=True)
    else:
        # Infrastructure failure is a diagnostic trace and never an official score.
        records.append(dict(type="result", **result))
        ui = project(records, source_hash=file_hash)
        if result.get("ticks") != world.tick or result.get("stats") != stats:
            raise ValueError("Public failure statistics differ from confirmed frames")
    origin = value.get("origin_source_sha256") or value.get("source_sha256")
    if not isinstance(origin, str) or not re.fullmatch(r"[0-9a-f]{64}", origin):
        raise ValueError("Public Replay requires its original evidence hash association")
    ui.update(projection_version=2, partial=False, verification="public_world_only", origin_source_sha256=origin,
              origin_association="unverified_claim", bot_rerunnable=False)
    return ui
