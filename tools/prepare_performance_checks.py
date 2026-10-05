"""Select verified, genuine 500-Tick evidence for repeatable browser measurements."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.io import read_json, sha_file, write_json
from service.imports import import_bundled
from service.store import Store
from service.replays import decode, MAX_REPLAY_BYTES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True)
    parser.add_argument('--proof', required=True)
    parser.add_argument('--add-size-boundary', action='store_true')
    args = parser.parse_args()
    root = Path(args.data).resolve()
    if args.add_size_boundary:
        proof = read_json(args.proof)
        store = Store(root)
        row = store.get('match', proof['match_id'])
        original = Path(row['replay']).read_bytes()
        if sha_file(row['replay']) != proof['source_sha256']:
            raise ValueError('Source changed after selection')
        lines = original.splitlines(keepends=True)
        per_line, remainder = divmod(MAX_REPLAY_BYTES - len(original), len(lines))
        reformatted = b''.join(line[:-1] + b' ' * (per_line + (i < remainder)) + line[-1:]
                              for i, line in enumerate(lines))
        if len(reformatted) != MAX_REPLAY_BYTES or decode(reformatted) != decode(original):
            raise ValueError('Boundary formatting changed records')
        path = root / 'boundary-replay.jsonl'
        path.write_bytes(reformatted)
        proof['size_boundary'] = dict(replay_bytes=len(reformatted), source_sha256=sha_file(path),
                original_source_sha256=proof['source_sha256'], records_equal=True,
                file=str(path.relative_to(Path(__file__).resolve().parents[1])).replace('\\', '/'),
                method='JSON whitespace only, distributed before line endings; decoded records equal original genuine trace')
        write_json(args.proof, proof)
        print('Prepared exactly 16 MiB with all decoded records unchanged.')
        return
    if (root / 'arena.sqlite3').exists():
        raise FileExistsError('Use a new performance workspace')
    store = Store(root)
    import_bundled(store)
    candidates = []
    for row in store.list('match'):
        if row['status'] != 'completed' or row['ticks'] != 500 or not row['verified']:
            continue
        projection = read_json(row['projection'])
        moves = sum(e['type'] == 'move' for f in projection['frames'] for e in f['events'])
        candidates.append((moves, Path(row['replay']).stat().st_size, row))
    moves, size, row = max(candidates, key=lambda item: item[:2])
    if size > 16 * 1024 * 1024:
        raise ValueError('Replay exceeds delivery size bound')
    write_json(args.proof, dict(kind='genuine_verified_500_tick_performance_fixture',
               match_id=row['id'], ticks=500, frames=501, moves=moves,
               selection='most successful movements, then largest raw size among verified 500-Tick reference traces',
               source_sha256=sha_file(row['replay']), replay_bytes=size,
               projection_bytes=Path(row['projection']).stat().st_size,
               qualified_entrants=[e['id'] for e in store.list('entrant') if e['status'] == 'qualified'],
               candidate_count=len(candidates), largest_candidate_bytes=max(c[1] for c in candidates)))
    print(f'Selected {row["id"]}: 500 ticks, {moves} moves, {size} raw bytes.')


if __name__ == '__main__':
    main()
