"""Build an allowlisted Windows development arena without organizer/private data."""
import argparse
from pathlib import Path
import re
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.compiler import compile_bot
from runner.io import ROOT, read_json, sha_file, write_json
from runner.match import qualify
from runtime.wasm import Backend


def package(output):
    output = Path(output).resolve()
    if output.exists() or output.with_suffix('.sha256').exists():
        raise ValueError("Choose a new ZIP path; existing distribution files are not overwritten")
    names = ["MODEL_TASK.md", "arena.py", "requirements.lock", "configs/toolchain.json", "configs/public-dev.json",
             "tools/setup.ps1", "tools/bootstrap.py", "tools/practice.py", "tools/build_devkit.py", "sdk/arena.hpp", "sdk/wrapper.cpp", "sdk/template.cpp",
             "docs/guides/model-development.md"]
    for folder in ("engine", "runtime", "runner", "replay"):
        names += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / folder).glob('*.py'))]
    names += [f'bots/baselines/{name}' for name in ('random.cpp', 'safe.cpp', 'heuristic.cpp', 'planner.hpp')]
    names += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'docs/specs').glob('*.md'))]
    # Guide links remain useful; references outside this public package are plain text.
    included = set(names)
    def public_document(name):
        text = (ROOT / name).read_text(encoding='utf-8')
        def link(match):
            label, target = match.group(1), match.group(2)
            if not target.startswith(('./', '../')):
                return match.group(0)
            key = (ROOT / name).parent.joinpath(target.split('#', 1)[0]).resolve().relative_to(ROOT).as_posix()
            return match.group(0) if key in included else label
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, text)
    with tempfile.TemporaryDirectory(prefix='llm-arena-devkit-') as folder:
        stage = Path(folder).resolve()
        assert stage.is_relative_to(Path(tempfile.gettempdir()).resolve())
        files = {name: (public_document(name).encode('utf-8') if name.endswith('.md') and name != 'MODEL_TASK.md'
                        else (ROOT / name).read_bytes()) for name in names}
        files['README.md'] = public_document('docs/guides/model-development.md').replace('../../', './').encode('utf-8')
        qualification = {}
        with Backend() as backend:
            for name in ('random', 'safe', 'heuristic'):
                target = stage / f'{name}.wasm'
                meta = compile_bot(ROOT / f'bots/baselines/{name}.cpp', target)
                result = qualify(backend, target)
                qualification[name] = dict(status=result['status'], wasm_sha256=result['wasm_sha256'],
                                           source_sha256=meta['source_sha256'], compiler_sha256=meta['compiler_sha256'],
                                           init_fuel_used=result['init_fuel_used'], smoke_call=result['smoke_call'])
                files[f'bots/baselines/{name}.wasm'] = target.read_bytes()
        import hashlib
        manifest = dict(format='llm-arena-public-devkit', version=1, platform='windows-x64', ruleset='1',
                        public_cases=10, toolchain=read_json(ROOT / 'configs/toolchain.json'),
                        qualifications=qualification,
                        files={name: dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest()) for name, data in sorted(files.items())})
        write_json(stage / 'devkit-manifest.json', manifest)
        files['devkit-manifest.json'] = (stage / 'devkit-manifest.json').read_bytes()
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipped:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                zipped.writestr(info, data)
        checksum = sha_file(output)
        output.with_suffix('.sha256').write_text(f'{checksum}  {output.name}\n', encoding='utf-8')
    print(f'Public devkit: {output} ({output.stat().st_size} bytes)')
    print(f'SHA-256: {checksum}; {len(files)} files, three qualified baselines, ten public maps.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        package(args.output)
    except (ValueError, OSError) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
