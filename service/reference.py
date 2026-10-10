"""Build reference games from the current public sources, without release archives."""
from pathlib import Path
import zipfile

from engine.model import digest
from runner.compiler import compile_bot
from runner.io import ROOT, read_json, sha_file, write_json, write_lines
from runner.match import components, run_match
from runner.report import generate_report
from runner.tournament import run_tournament
from runtime.wasm import Backend


def reference_key():
    return digest(dict(components=components(), generator=sha_file(__file__)))


def build_reference(folder):
    """Generate 300 public baseline games and a scripted chain explosion example."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    entrants = []
    for name in ('heuristic', 'random', 'safe'):
        wasm = folder / 'build' / f'{name}.wasm'
        compile_bot(ROOT / f'bots/baselines/{name}.cpp', wasm)
        entrants.append(dict(id=name, wasm=str(wasm.resolve())))
    cases = read_json(ROOT / 'configs/acceptance-cases.json')
    run_tournament(entrants, cases, folder, resume=(folder / 'manifest.json').exists())
    generate_report(folder)
    example = folder / 'examples/chain'
    example.mkdir(parents=True, exist_ok=True)
    chain = []
    for name in ('a', 'b'):
        wasm = example / f'{name}.wasm'
        compile_bot(ROOT / f'bots/examples/chain-{name}.cpp', wasm)
        chain.append(dict(id=f'chain-{name}', wasm=str(wasm.resolve())))
    with Backend() as backend:
        _, records = run_match(backend, chain, 102, [1, 2], 'chain')
    write_lines(example / 'replay.jsonl', records)
    write_json(folder / 'reference.json', dict(source_key=reference_key()))
    return folder


def reference_archive():
    """Reusable generated fixture for tests and browser uploads; ignored by Git."""
    folder = ROOT / 'artifacts/work/reference' / reference_key()
    archive = folder.with_suffix('.zip')
    if not archive.is_file():
        build_reference(folder)
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as target:
            for path in sorted(folder.rglob('*')):
                if path.is_file():
                    target.write(path, path.relative_to(folder).as_posix())
    return archive
