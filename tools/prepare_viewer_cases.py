"""Generate genuine WASM/rules traces for spectator acceptance, never model scores."""
import argparse
from collections import deque
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.maps import generate
from engine.model import DIRECTIONS, FLOOR, WAIT, BOMB
from runner.io import sha_file, write_json
from runner.match import run_match
from runtime.wasm import Backend
from service.imports import import_bundled, import_replay
from service.replays import from_bytes
from service.store import Store
from tests.test_runtime import module


def scripted(actions, trap_at=None):
    data = ''.join(f'\\{byte:02x}' for action in actions for byte in struct.pack('<I', action))
    prefix = (f'i32.const 0 i32.load offset=4 i32.const {trap_at} i32.eq if unreachable end '
              if trap_at is not None else '')
    body = prefix + f'''i32.const 0 i32.load offset=4 i32.const {len(actions)} i32.lt_u
        if (result i32)
          i32.const 65536 i32.const 0 i32.load offset=4 i32.const 4 i32.mul i32.add i32.load
        else i32.const 0 end'''
    return module(body, extra=f'(data (i32.const 65536) "{data}")')


def open_path(m):
    start, end = map(tuple, m['spawns'])
    paths, pending = {start: [start]}, deque([start])
    while pending:
        p = pending.popleft()
        if p == end:
            return paths[p]
        for dx, dy in DIRECTIONS.values():
            q = p[0]+dx, p[1]+dy
            if q not in paths and m['grid'][q[1]*13+q[0]] == FLOOR:
                paths[q] = paths[p]+[q]
                pending.append(q)


def route(points):
    by_delta = {delta: action for action, delta in DIRECTIONS.items()}
    return [by_delta[b[0]-a[0], b[1]-a[1]] for a, b in zip(points, points[1:])]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True)
    parser.add_argument('--proof', required=True)
    args = parser.parse_args()
    root = Path(args.data).resolve()
    if root.exists():
        raise ValueError('Use a new acceptance directory')
    store = Store(root)
    import_bundled(store)
    long_name = 'Heuristic（工程长名称展示检查）' + 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'*2
    store.update('entrant', 'heuristic', lambda row: row.update(name=long_name))
    specs = [
        ('init-both', '双方初始化失败', 1, module(init='unreachable'), module(init='unreachable')),
        ('init-one', '单方初始化失败', 1, module(init='unreachable'), module()),
        ('fuel', '连续 fuel 动作故障', 1, module('(loop $l br $l) i32.const 0'), module()),
        ('invalid', '连续非法动作', 1, module('i32.const 99'), module()),
        ('trap', 'Tick 运行崩溃', 1, module('unreachable'), module()),
        ('blocked', '合法移动被硬墙阻挡', 1, scripted([1]), module()),
        ('infra', '持久输出失败', 1, module(), module()),
    ]
    for seed in range(1, 10001):
        m = generate(seed)
        if all(m['grid'][y*13+x] == FLOOR for x, y in [(3, 1), (3, 2)]):
            specs.append(('escape', 'T+4 爆炸与后续无火焰', seed, scripted([BOMB, 2, 2, 3]), module()))
            break
    else:
        raise ValueError('No escape example found')
    for seed in range(1, 10001):
        path = open_path(generate(seed))
        if path:
            middle = (len(path)-1)//2
            a, b = route(path[:middle+1]), route(list(reversed(path[middle+1:])))
            place = max(len(a), len(b))
            a += [WAIT]*(place-len(a)) + [BOMB] + [WAIT]*4
            b += [WAIT]*(place-len(b)) + [WAIT]*4 + [BOMB]
            specs.append(('new-chain', '到期炸弹连锁引爆本 Tick 新炸弹', seed, scripted(a), scripted(b)))
            specs.append(('dead-owner', 'owner 崩溃后炸弹仍在本 Tick 爆炸', seed, scripted(a, place+4), scripted(b)))
            break
    else:
        raise ValueError('No connected floor route found')
    proofs = []
    with Backend() as backend:
        for name, title, seed, first, second in specs:
            entrants = []
            for slot, code in enumerate((first, second)):
                eid = f'viewer-{name}-{slot}'
                path = root/'fixture-modules'/f'{eid}.wasm'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(code)
                store.put('entrant', dict(id=eid, name=f'规则检查 {name} / {slot}',
                                         model='工程 WASM 检查，不是模型生成', wasm_sha256=sha_file(path),
                                         status='historical', baseline=False))
                entrants.append(dict(id=eid, wasm=str(path)))
            def sink(record):
                if name == 'infra' and record['type'] == 'tick' and record['tick'] == 2:
                    raise OSError('Acceptance durable output failure')
            raw = root/'fixture-traces'/f'{name}.jsonl'
            result, records = run_match(backend, entrants, seed, [1, 2], f'viewer-{name}',
                                        replay_path=raw, record_sink=sink)
            row = import_replay(store, raw.read_bytes(), identity=f'viewer-{name}', title=f'工程规则检查：{title}')
            ui = from_bytes(raw.read_bytes())
            if name == 'escape':
                assert result['valid'] and result['ticks'] == 500
                assert ui['frames'][5]['visual']['coverage'] and not ui['frames'][6]['visual']['coverage']
            if name == 'new-chain':
                assert any(b['chain'] and b['explode_at_tick'] == f['tick']+4
                           for f in ui['frames'] for b in f['visual']['exploded_bombs'])
            if name == 'dead-owner':
                assert any(e['type'] == 'death' and e['cause'] == 'runtime' for e in records[-2]['events'])
                assert ui['frames'][-1]['visual']['exploded_bombs']
            proofs.append(dict(id=row['id'], title=title, source_sha256=row['source_sha256'],
                               wasm_sha256=[sha_file(e['wasm']) for e in entrants], valid=result['valid'],
                               reason=result['reason'], ticks=result['ticks'], frames=len(ui['frames']),
                               last_frame_events=ui['frames'][-1]['events']))
    write_json(args.proof, dict(kind='engineering_wasm_not_model_submissions', cases=proofs))
    print(f'Created {len(proofs)} actual WASM spectator cases and verified their projections.')


if __name__ == '__main__':
    main()
