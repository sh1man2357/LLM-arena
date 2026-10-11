"""Build an allowlisted Windows development arena without organizer/private data."""
import argparse
from pathlib import Path
import re
import sys
import tempfile
import zipfile
import posixpath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.compiler import compile_bot
from runner.io import ROOT, read_json, sha_file, write_json
from runner.match import qualify, run_match
from engine.model import Rules
from replay.verify import verify_world
from runtime.wasm import Backend


def package(output, game_id="bomberman"):
    if game_id not in ("bomberman", "gomoku"):
        raise ValueError("Unknown game")
    gomoku = game_id == "gomoku"
    output = Path(output).resolve()
    if output.exists() or output.with_suffix('.sha256').exists():
        raise ValueError("Choose a new ZIP path; existing distribution files are not overwritten")
    names = ["devkit/START_HERE.md", "devkit/start-devkit.ps1", "devkit/MODEL_TASK.md", "arena.py", "requirements.lock", "configs/toolchain.json", "configs/public-dev.json",
             "tools/setup.ps1", "tools/bootstrap.py", "tools/devkit_ready.py", "tools/practice.py", "tools/build_devkit.py", "sdk/arena.hpp", "sdk/wrapper.cpp", "sdk/template.cpp",
             "docs/guides/model-development.md"]
    if gomoku:
        names = [n for n in names if n not in ("devkit/START_HERE.md", "devkit/MODEL_TASK.md")]
        names += ["devkit/GOMOKU_START_HERE.md", "devkit/GOMOKU_MODEL_TASK.md"]
    names += ["configs/gomoku-public-dev.json", "tools/gomoku_practice.py", "sdk/gomoku/gomoku.hpp", "sdk/gomoku/wrapper.cpp", "sdk/gomoku/template.cpp"]
    for folder in ("engine", "gomoku", "runtime", "runner", "replay"):
        names += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / folder).glob('*.py'))]
    names += [f'bots/baselines/{name}' for name in ('random.cpp', 'safe.cpp', 'heuristic.cpp', 'planner.hpp')]
    names += [f'bots/gomoku/{name}' for name in ('random.cpp', 'tactical.cpp', 'search.cpp', 'planner.hpp')]
    names += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'docs/specs').glob('*.md'))]
    # Guide links remain useful; references outside this public package are plain text.
    targets = {name: name.removeprefix('devkit/') for name in names}
    if gomoku:
        targets.update({'devkit/GOMOKU_START_HERE.md': 'START_HERE.md', 'devkit/GOMOKU_MODEL_TASK.md': 'MODEL_TASK.md'})
    def public_document(name):
        text = (ROOT / name).read_text(encoding='utf-8')
        def link(match):
            label, target = match.group(1), match.group(2)
            if not target.startswith(('./', '../')):
                return match.group(0)
            key = (ROOT / name).parent.joinpath(target.split('#', 1)[0]).resolve().relative_to(ROOT).as_posix()
            if key not in targets:
                return label
            relative = posixpath.relpath(targets[key], posixpath.dirname(targets[name]) or '.')
            return f'[{label}]({relative})'
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, text)
    with tempfile.TemporaryDirectory(prefix='llm-arena-devkit-') as folder:
        stage = Path(folder).resolve()
        assert stage.is_relative_to(Path(tempfile.gettempdir()).resolve())
        files = {targets[name]: (public_document(name).encode('utf-8') if name.endswith('.md') and name not in ('devkit/MODEL_TASK.md', 'devkit/GOMOKU_MODEL_TASK.md')
                        else (ROOT / name).read_bytes()) for name in names}
        files['README.md'] = files['START_HERE.md']
        qualification = {}
        with Backend() as backend:
            for name in (('random', 'tactical', 'search') if gomoku else ('random', 'safe', 'heuristic')):
                target = stage / f'{name}.wasm'
                folder_name = 'gomoku' if gomoku else 'baselines'
                meta = compile_bot(ROOT / f'bots/{folder_name}/{name}.cpp', target, game_id)
                result = qualify(backend, target, game_id)
                if gomoku:
                    from gomoku.match import run_match as gomoku_run
                    smoke, records = gomoku_run(backend, [dict(id=name, wasm=str(target))]*2,
                                                1, [1, 2], opening_mode='library')
                else:
                    smoke, records = run_match(backend, [dict(id=name, wasm=str(target)) for _ in range(8)],
                                               1, list(range(1, 9)), rules=Rules(max_ticks=2))
                verify_world(records)
                qualification[name] = dict(status=result['status'], wasm_sha256=result['wasm_sha256'],
                                           source_sha256=meta['source_sha256'], compiler_sha256=meta['compiler_sha256'],
                                           init_fuel_used=result['init_fuel_used'], smoke_call=result['smoke_call'],
                                           multiplayer_smoke=dict(status='verified', player_count=2 if gomoku else 8, ticks=smoke['ticks']))
                files[f'bots/{folder_name}/{name}.wasm'] = target.read_bytes()
        import hashlib
        manifest = dict(format='llm-arena-public-devkit', version=3, game_id=game_id, platform='windows-x64', ruleset='1',
                        game_mode='paired_colors' if gomoku else 'free_for_all', player_counts=[2] if gomoku else list(range(2, 9)),
                        map_generator='1' if gomoku else '2', public_cases=12 if gomoku else 10,
                        toolchain=read_json(ROOT / 'configs/toolchain.json'),
                        qualifications=qualification,
                        files={name: dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest()) for name, data in sorted(files.items())})
        write_json(stage / 'devkit-manifest.json', manifest)
        files['devkit-manifest.json'] = (stage / 'devkit-manifest.json').read_bytes()
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipped:
            # Put the explicit task instruction first for attachment readers.
            for name in sorted(files, key=lambda name: (name != 'README.md', name)):
                data = files[name]
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                zipped.writestr(info, data)
        checksum = sha_file(output)
        output.with_suffix('.sha256').write_text(f'{checksum}  {output.name}\n', encoding='utf-8')
    print(f'Public devkit: {output} ({output.stat().st_size} bytes)')
    print(f'SHA-256: {checksum}; {len(files)} files, {game_id}, three qualified baselines, {manifest["public_cases"]} public cases.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', choices=('bomberman', 'gomoku'), default='bomberman')
    parser.add_argument('--output')
    args = parser.parse_args()
    try:
        package(args.output or ('artifacts/distribution/llm-arena-gomoku-devkit.zip' if args.game == 'gomoku' else 'artifacts/distribution/llm-arena-devkit.zip'), args.game)
    except (ValueError, OSError) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
