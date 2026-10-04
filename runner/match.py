from dataclasses import asdict
from pathlib import Path
from engine.maps import generate
from engine.model import Player, Rules, World, digest
from engine.rules import step
from runtime.protocol import encode
from runtime.wasm import Backend, InitializationError, InfrastructureError, INIT_FUEL, TICK_FUEL
from runner.io import ROOT, read_json, sha_file, write_lines


def components():
    files = {}
    for folder in ("engine", "runtime", "runner", "replay", "sdk", "bots", "configs"):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and path.suffix in (".py", ".hpp", ".cpp", ".json") and "__pycache__" not in path.parts:
                files[path.relative_to(ROOT).as_posix()] = sha_file(path)
    return dict(benchmark_id="bomber-v0.1", ruleset="1", map_generator="1", sdk="1", baseline_set="1",
                reporter="1", runtime="wasmtime-49.0.0", toolchain=read_json(ROOT / "configs/toolchain.json"),
                source_hash=digest(files), source_files=files)


def qualify(backend, path):
    module = backend.load(path)
    instance = backend.instance(module, 1)
    try:
        m = generate(1)
        world = World(m["width"], m["height"], m["grid"], [Player(i, *p) for i, p in enumerate(m["spawns"])])
        call = instance.call(encode(world, 0))
        if call["fault"]:
            raise ValueError(f"Public smoke check failed: {call['fault']}")
        return dict(status="qualified", wasm_sha256=sha_file(path), smoke_call=call,
                    init_fuel_used=instance.init_fuel_used)
    finally:
        instance.close()


def empty_stats():
    return dict(calls=0, fuel_used=0, max_tick_fuel=0, action_faults=0, fuel_exhaustions=0,
                runtime_eliminations=0, initialization_failures=0, explosion_deaths=0,
                kills=0, self_kills=0, mixed_deaths=0, bombs_placed=0)


def account(stats, calls, events):
    for pid, call in calls.items():
        row = stats[pid]
        row["calls"] += 1
        row["fuel_used"] += call.get("fuel_used", 0)
        row["max_tick_fuel"] = max(row["max_tick_fuel"], call.get("fuel_used", 0))
        row["action_faults"] += call.get("fault") in ("fuel", "invalid_action")
        row["fuel_exhaustions"] += call.get("fault") == "fuel"
    for event in events:
        if event["type"] == "place":
            stats[event["owner"]]["bombs_placed"] += 1
        if event["type"] != "death":
            continue
        pid = event["player"]
        if event["cause"] == "runtime":
            stats[pid]["runtime_eliminations"] += 1
            continue
        stats[pid]["explosion_deaths"] += 1
        owners = event["owners"]
        if owners == [pid]:
            stats[pid]["self_kills"] += 1
        elif len(owners) == 1:
            stats[owners[0]]["kills"] += 1
        else:
            stats[pid]["mixed_deaths"] += 1


def make_result(world, stats, match_id, reason=None):
    groups, scores = world.standings()
    return dict(type="result", match_id=match_id, valid=True, reason=reason or world.end_reason(),
                ticks=world.tick, survivors=[p.id for p in world.players if p.alive],
                groups=groups, players=scores, stats=stats, final_state_hash=world.state_hash())


def run_match(backend, entrants, map_seed, bot_seeds, match_id="single", rules=None,
              replay_path=None, init_fuel=INIT_FUEL, tick_fuel=TICK_FUEL, version=None):
    if len(entrants) != 2 or len(bot_seeds) != 2 or len({e["id"] for e in entrants}) != 2:
        raise ValueError("v0.1 matches require two distinct entrants and two seeds")
    rules = rules or Rules()
    m = generate(map_seed)
    world = World(m["width"], m["height"], m["grid"], [Player(i, *p) for i, p in enumerate(m["spawns"])], rules)
    modules = [backend.load(e["wasm"]) for e in entrants]  # Qualification errors are not match losses.
    stats = [empty_stats(), empty_stats()]
    init_records, instances = [], {}
    records = []
    try:
        for pid, module in enumerate(modules):
            try:
                instances[pid] = backend.instance(module, bot_seeds[pid], init_fuel, tick_fuel)
                init_records.append(dict(id=pid, status="ok", fuel_used=instances[pid].init_fuel_used))
            except InitializationError as exc:
                world.players[pid].alive, world.players[pid].death_tick = False, -1
                stats[pid]["initialization_failures"] = 1
                init_records.append(dict(id=pid, status="eliminated", diagnostic=str(exc)))
        header = dict(type="header", schema_version=1, match_id=match_id, components=version or components(),
                      rules=asdict(rules), map=m, map_seed=map_seed,
                      bot_seeds=[f"{s:016x}" for s in bot_seeds],
                      entrants=[dict(id=e["id"], slot=i, wasm_sha256=sha_file(e["wasm"])) for i, e in enumerate(entrants)],
                      budget=dict(init_fuel=init_fuel, tick_fuel=tick_fuel), initialization=init_records,
                      initial_state=world.state(), initial_state_hash=world.state_hash())
        records.append(header)
        initial_end = world.end_reason() is not None
        while not world.end_reason():
            before = world.state_hash()
            calls = {p.id: instances[p.id].call(encode(world, p.id)) for p in world.players if p.alive}
            t = world.tick
            actions, events = step(world, calls)
            account(stats, calls, events)
            records.append(dict(type="tick", tick=t, before_hash=before,
                                calls=[dict(id=pid, **calls[pid]) for pid in sorted(calls)],
                                actions=[dict(id=pid, action=actions[pid]) for pid in sorted(actions)],
                                events=events, state=world.state(), after_hash=world.state_hash()))
        result = make_result(world, stats, match_id, "initialization_end" if initial_end else None)
        records.append(result)
    except InfrastructureError as exc:
        result = dict(type="result", match_id=match_id, valid=False, reason="infrastructure_failure",
                      diagnostic=str(exc), ticks=world.tick, players=[], stats=stats)
        records.append(result)
    finally:
        for instance in instances.values():
            instance.close()
    if replay_path:
        write_lines(replay_path, records)
    return result, records
