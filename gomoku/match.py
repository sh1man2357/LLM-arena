from copy import deepcopy
import struct

from gomoku import INIT_FUEL, MOVE_FUEL, RULES, SIZE, RESIGN
from gomoku.rules import World, opening, empty_stats, account, result
from runner.io import sha_file, write_lines
from runtime.wasm import InitializationError


def encode(world, self_id):
    last = world.moves[-1] if world.moves else dict(x=0xffffffff, y=0xffffffff)
    return struct.pack("<12I", 0x314d4f47, 1, SIZE, SIZE, self_id, self_id+1,
                       world.turn_color, len(world.moves), last["x"], last["y"], MOVE_FUEL, 5) + bytes(world.grid)


def qualify(backend, path):
    instance = backend.instance(backend.load(path), 1, INIT_FUEL, MOVE_FUEL)
    instance.action_max = RESIGN
    try:
        call = instance.call(encode(World(), 0))
        if call["fault"]:
            raise ValueError(f"Public Gomoku smoke check failed: {call['fault']}")
        return dict(status="qualified", game_id="gomoku", wasm_sha256=sha_file(path),
                    smoke_call=call, init_fuel_used=instance.init_fuel_used)
    finally:
        instance.close()


def run_match(backend, entrants, map_seed, bot_seeds, match_id="single", *, opening_mode="empty",
              replay_path=None, record_sink=None):
    from runner.match import components
    if len(entrants) != 2 or len(bot_seeds) != 2:
        raise ValueError("Gomoku requires two Bots and two seeds")
    world = World(opening(map_seed, opening_mode))
    modules = [backend.load(e["wasm"]) for e in entrants]
    stats = [empty_stats(), empty_stats()]
    init, instances = [], {}
    header = dict(type="header", schema_version=1, game_id="gomoku", match_id=match_id,
                  components=components("gomoku"), rules=RULES.copy(), map_seed=map_seed, opening_mode=opening_mode,
                  map=dict(width=SIZE, height=SIZE, moves=deepcopy(world.moves)),
                  bot_seeds=[f"{s:016x}" for s in bot_seeds],
                  entrants=[dict(id=e["id"], slot=i, wasm_sha256=sha_file(e["wasm"])) for i, e in enumerate(entrants)],
                  budget=dict(init_fuel=INIT_FUEL, tick_fuel=MOVE_FUEL), initialization=init,
                  initial_state=world.state(), initial_state_hash=world.state_hash())
    records = [header]
    def emit(record):
        if record_sink:
            record_sink(deepcopy(record))
    try:
        for pid, module in enumerate(modules):
            try:
                instances[pid] = backend.instance(module, bot_seeds[pid], INIT_FUEL, MOVE_FUEL)
                instances[pid].action_max = RESIGN
                init.append(dict(id=pid, status="ok", fuel_used=instances[pid].init_fuel_used))
            except InitializationError as exc:
                init.append(dict(id=pid, status="eliminated", diagnostic=str(exc)))
                stats[pid]["initialization_failures"] = 1
        world.initialize(init)
        header.update(initial_state=world.state(), initial_state_hash=world.state_hash())
        emit(header)
        while not world.reason:
            t, before, pid = world.tick, world.state_hash(), world.turn_id
            calls = {pid: instances[pid].call(encode(world, pid))}
            actions, events = world.step(calls)
            account(stats, calls, events)
            records.append(dict(type="tick", tick=t, before_hash=before,
                                calls=[dict(id=pid, **calls[pid])], actions=[dict(id=pid, action=actions[pid])],
                                events=events, state=world.state(), after_hash=world.state_hash()))
            emit(records[-1])
        records.append(result(world, stats, match_id))
        emit(records[-1])
    except Exception as exc:
        if records[-1].get("type") == "result":
            records.pop()
        records.append(dict(type="result", game_id="gomoku", match_id=match_id, valid=False,
                            reason="infrastructure_failure", ticks=world.tick, players=[], stats=stats,
                            diagnostic=f"{type(exc).__name__}: {exc}"))
        try:
            emit(records[-1])
        except Exception:
            pass
    finally:
        for instance in instances.values():
            instance.close()
    if replay_path:
        write_lines(replay_path, records)
    return records[-1], records
