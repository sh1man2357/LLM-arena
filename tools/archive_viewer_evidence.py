"""Package only the final recorded viewer screenshots/video and verified check files."""
import argparse
from pathlib import Path
import platform
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.io import ROOT, read_json, sha_file, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='artifacts/acceptance/v0.2-development')
    parser.add_argument('--regression-log', help='Fresh full eight-flow Playwright results.json')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if args.regression_log:
        regression = read_json(args.regression_log)
        stats = regression['stats']
        if stats['expected'] != 8 or stats['unexpected'] or stats['skipped'] or stats['flaky']:
            raise ValueError('Fresh full browser regression must pass all eight flows')
        write_json(output/'checks/browser-viewer-quality.json', regression)
    visual = output/'visual/viewer-quality'
    proof = read_json(output/'checks/viewer-quality.json')
    if proof['status'] != 'passed' or proof['page_errors']:
        raise ValueError('Viewer verification must pass before packaging')
    names = [*proof['screenshots'], proof['video']]
    if len(names) != len(set(names)) or any(Path(name).name != name for name in names):
        raise ValueError('Evidence must use unique local filenames')
    rows = [dict(file=name, bytes=(visual/name).stat().st_size, sha256=sha_file(visual/name)) for name in names]
    checks = ['viewer-cases.json', 'viewer-quality.json', 'browser-viewer-quality.json']
    regression = read_json(output/'checks/browser-viewer-quality.json')
    if regression.get('status') == 'passed_after_targeted_retry':
        checks += [regression['initial_file'], regression['retry_file']]
    elif regression.get('stats', {}).get('expected') != 8 or regression['stats']['unexpected']:
        raise ValueError('Missing passing browser regression evidence')
    archive = output/'visual/viewer-quality.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as target:
        for name in names:
            target.write(visual/name, f'visual/{name}')
        for name in checks:
            target.write(output/'checks'/name, f'checks/{name}')
    with zipfile.ZipFile(archive) as target:
        if target.testzip() is not None:
            raise ValueError('Archive failed CRC verification')
    sources = ['tools/prepare_viewer_cases.py', 'tools/archive_viewer_evidence.py',
               'web/tools/verify-viewer-quality.mjs', 'web/tools/check-contrast.mjs',
               *[p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'web/src').glob('*')) if p.is_file()],
               'web/tests/spectator.spec.ts', 'web/tests/zz_recovery.spec.ts',
               'web/package-lock.json', 'requirements-service.lock']
    write_json(output/'checks/viewer-stage.json', dict(
        platform=platform.platform(), python=sys.version, browser=proof['browser'],
        source_files_sha256={name: sha_file(ROOT/name) for name in sources},
        proof_files_sha256={name: sha_file(output/'checks'/name) for name in checks},
        archive=dict(file='visual/viewer-quality.zip', bytes=archive.stat().st_size, sha256=sha_file(archive), files=rows),
        scope='Rendered engineering WASM cases; not real model submissions or final human aesthetic approval',
    ))
    print(f'Packaged {len(rows)} visual files with hashes and verified archive CRC.')


if __name__ == '__main__':
    main()
