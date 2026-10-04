"""Verified, seed-free spectator projection of schema-1 competition evidence."""
from copy import deepcopy
import hashlib
import json

from engine.model import Bomb, Rules, World
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
    frames = [dict(seq=0, tick=None, state=deepcopy(previous), events=[], actions=[], calls=[],
                   visual=dict(coverage=[], exploded_bombs=[], blocked_moves=[]))]
    for record in records[1:]:
        if record["type"] == "result":
            continue
        if record["type"] != "tick" or record["tick"] != previous["tick"]:
            raise ValueError("Nonsequential Replay")
        world = World.from_state(13, 11, rules, previous)
        calls = {c["id"]: {k: v for k, v in c.items() if k != "id"} for c in record["calls"]}
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
    return dict(schema_version=1, projection_version=1, source_sha256=source_hash,
                match_id=h["match_id"], width=13, height=11,
                entrants=[{k: e[k] for k in ("id", "slot", "wasm_sha256")} for e in h["entrants"]], rules=h["rules"],
                budget=h["budget"], initialization=[{k: v for k, v in row.items() if k != "diagnostic"}
                                                    for row in h["initialization"]],
                verified=verified, partial=not terminal, frames=frames, result=public_result,
                components={k: h["components"].get(k) for k in ("benchmark_id", "ruleset", "map_generator", "sdk", "runtime", "source_hash")})


def from_bytes(data):
    return project(decode(data), source_hash=hashlib.sha256(data).hexdigest())
