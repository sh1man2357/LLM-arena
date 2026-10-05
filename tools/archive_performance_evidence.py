"""Validate final measurements and package rendered evidence without private data."""
import argparse
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.io import ROOT, read_json, write_json, sha_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='artifacts/acceptance/v0.2-development')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    checks = output / 'checks'
    for name in ('performance-final.json', 'performance-boundary.json'):
        proof = read_json(checks / name)
        if proof['status'] != 'passed' or proof['page_errors']:
            raise ValueError(f'Final performance must pass: {name}')
        if len(proof['navigations']) != 12 or len(proof['seeks']) != 144 or len(proof['animations']) != 4:
            raise ValueError('Incomplete viewport/repetition scope')
        if any(n['first_paint_ms'] > 1500 for n in proof['navigations']) or any(s['latency_ms'] > 100 for s in proof['seeks']):
            raise ValueError('Paint/seek threshold failed')
        if any(a['canvas_animation_fps'] < 55 or a['player0_interpolation_reversals'] for a in proof['animations']):
            raise ValueError('Playback threshold or motion failed')
    background = read_json(checks / 'performance-background-final.json')
    if background['status'] != 'measured' or background['page_errors'] or {w['kind'] for w in background['work']} != {'compile', 'match'}:
        raise ValueError('Both real background jobs must be measured')
    for job in background['work']:
        if job['bracketed_samples'] < 3 or job['seek_ms']['max'] > 100 or job['final_job']['status'] != 'succeeded':
            raise ValueError('Background operation evidence incomplete')
        if job['playback']['before_status'] != 'running' or job['playback']['after_status'] != 'running' or job['playback']['player0_interpolation_reversals']:
            raise ValueError('Playback must occur entirely inside the running job')
    full = read_json(checks / 'browser-performance-regression.json')
    regression = full['stats']
    def specs(suites):
        for suite in suites:
            yield from suite.get('specs', [])
            yield from specs(suite.get('suites', []))
    scope = {s['title']: bool(s['ok']) for s in specs(full['suites'])}
    retried = None
    if regression['expected'] != 8 or regression['unexpected']:
        retry = read_json(checks / 'browser-performance-archive-retry.json')
        if regression['expected'] != 7 or regression['unexpected'] != 1 or retry['stats']['expected'] != 1 or any(retry['stats'][k] for k in ('unexpected', 'flaky', 'skipped')):
            raise ValueError('Full seven plus corrected archive workflow must pass')
        retry_specs = list(specs(retry['suites']))
        retried = retry_specs[0]['title']
        if retried != 'host imports full legacy archive, compares swaps and downloads immutable publication' or scope.get(retried) is not False:
            raise ValueError('Retry must cover the actual failed workflow')
        scope[retried] = bool(retry_specs[0]['ok'])
    if len(scope) != 8 or not all(scope.values()) or any(regression[k] for k in ('flaky', 'skipped')):
        raise ValueError('All eight distinct browser workflows must pass')
    write_json(checks / 'browser-performance-summary.json', dict(status='passed', workflows=scope,
               method='full eight' if retried is None else 'seven successful workflows from full run, plus one complete corrected archive retry',
               full_run_sha256=sha_file(checks / 'browser-performance-regression.json'),
               retry_sha256=None if retried is None else sha_file(checks / 'browser-performance-archive-retry.json')))
    viewer = read_json(output / 'performance-regression-final/checks/viewer-quality.json')
    if viewer['status'] != 'passed' or len(viewer['checks']) != 14 or len(viewer['screenshots']) != 42 or viewer['page_errors']:
        raise ValueError('Full viewer regression must pass')
    live = read_json(checks / 'live-performance-recovery.json')
    if live['status'] != 'passed' or live['final_single_frames'] != 501 or live['valid_matches'] != 8 or live['page_errors']:
        raise ValueError('Real live/restart regression must pass')
    python = (checks / 'python-performance-final.log').read_text(encoding='utf-8')
    if not re.search(r'Ran 75 tests .*\n\s*\nOK', python):
        raise ValueError('Full Python regression must pass')
    paths = []
    for pattern in ('performance-*.*', 'browser-performance*.*', 'python-performance*.*', 'live-performance*.*'):
        paths.extend(p for p in checks.glob(pattern) if p.name != 'performance-stage.json')
    paths.extend(output.glob('visual/performance/*.png'))
    paths.append(output / 'performance-regression-final/checks/viewer-quality.json')
    visual = output / 'performance-regression-final/visual/viewer-quality'
    for name in [*viewer['screenshots'], viewer['video']]:
        if Path(name).name != name:
            raise ValueError('Only local media names are supported')
        paths.append(visual / name)
    paths = sorted(set(paths))
    manifest = [dict(file=p.relative_to(output).as_posix(), bytes=p.stat().st_size, sha256=sha_file(p)) for p in paths]
    archive = output / 'visual/performance-evidence.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as target:
        for path in paths:
            target.write(path, path.relative_to(output).as_posix())
    with zipfile.ZipFile(archive) as target:
        if target.testzip() is not None:
            raise ValueError('Archive failed CRC check')
    sources = ['service/app.py', 'service/store.py', 'tests/test_event_stream.py', 'web/src/Board.tsx',
               'web/src/Viewer.tsx', 'web/src/App.tsx', 'tools/prepare_performance_checks.py', 'tools/capture_performance_machine.ps1',
               'tools/archive_performance_evidence.py', 'web/tools/measure-performance.mjs',
               'web/tools/measure-background-work.mjs', 'web/tools/performance-instrumentation.mjs',
               'web/tools/verify-viewer-quality.mjs', 'web/tools/verify-live-recovery.mjs', 'web/tests/evidence.spec.ts']
    write_json(checks / 'performance-stage.json', dict(
        source_files_sha256={name: sha_file(ROOT / name) for name in sources},
        archive=dict(file='visual/performance-evidence.zip', bytes=archive.stat().st_size, sha256=sha_file(archive), files=manifest),
        final_checks=['performance-final.json', 'performance-boundary.json', 'performance-background-final.json',
                      'browser-performance-summary.json', 'python-performance-final.log', 'live-performance-recovery.json',
                      'performance-regression-final/checks/viewer-quality.json'],
        commands=[dict(command=command, cwd=cwd, exit_code=0) for cwd, command in [
            ('.', 'python tools/prepare_performance_checks.py --data artifacts/work/v0.2-performance-01 --proof artifacts/acceptance/v0.2-development/checks/performance-fixture.json'),
            ('.', 'python tools/prepare_performance_checks.py --data artifacts/work/v0.2-performance-01 --proof artifacts/acceptance/v0.2-development/checks/performance-fixture.json --add-size-boundary'),
            ('.', "& ./tools/capture_performance_machine.ps1 -Output artifacts/acceptance/v0.2-development/checks/performance-machine-repeat.json -Node 'C:\\syn-D\\nodejs\\node.exe'"),
            ('web', 'npm.cmd run build'),
            ('web', 'node tools/measure-performance.mjs http://127.0.0.1:8801 ../artifacts/acceptance/v0.2-development final'),
            ('web', 'node tools/measure-performance.mjs http://127.0.0.1:8801 ../artifacts/acceptance/v0.2-development boundary'),
            ('web', 'node tools/measure-background-work.mjs http://127.0.0.1:8801 ../artifacts/acceptance/v0.2-development final'),
            ('.', 'python -m unittest discover -s tests -v'),
            ('web', 'node tools/verify-viewer-quality.mjs http://127.0.0.1:8802 ../artifacts/acceptance/v0.2-development/performance-regression-final'),
            ('web', 'node tools/verify-live-recovery.mjs ../.venv/Scripts/python.exe ../artifacts/work/v0.2-performance-live-01 ../artifacts/acceptance/v0.2-development/checks/live-performance-recovery.json 8803')]] + [
                dict(command="$env:ARENA_BASE_URL='http://127.0.0.1:8801'; npm.cmd test", cwd='web', exit_code=0 if retried is None else 1),
                *([] if retried is None else [dict(command="npm.cmd test -- tests/evidence.spec.ts -g 'host imports full legacy'", cwd='web', environment=dict(ARENA_BASE_URL='http://127.0.0.1:8801'), exit_code=0)])],
        frozen_evidence_sha256={name: sha_file(ROOT / name) for name in [
            'artifacts/acceptance/v0.1-release/evidence.zip', 'artifacts/acceptance/v0.2-baselines/evidence.zip']}))
    print(f'Packaged {len(paths)} performance/regression files: {archive.stat().st_size} bytes, SHA-256 {sha_file(archive)}.')


if __name__ == '__main__':
    main()
