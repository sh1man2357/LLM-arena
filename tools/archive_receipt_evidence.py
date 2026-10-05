"""Preserve actual receipt/browser evidence without expanding release claims."""
import json
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.io import ROOT, read_json, write_json, sha_file


def main():
    output = ROOT / 'artifacts/acceptance/v0.2-development'
    checks = output / 'checks'
    reports = {}
    for name, count in [('browser-receipts', 4), ('browser-receipts-boundary', 1),
                        ('browser-receipts-regression', 26)]:
        report = read_json(checks / f'{name}.json')
        stats = report['stats']
        if stats['expected'] != count or any(stats[k] for k in ('unexpected','flaky','skipped')) or report['errors']:
            raise ValueError(f'Incomplete actual browser proof: {name}')
        reports[name] = stats
    python_log = (checks / 'python-receipts.log').read_text(encoding='utf-8')
    if not re.search(r'Ran 78 tests in [\d.]+s\s+OK\s*$', python_log):
        raise ValueError('Full Python regression incomplete')
    visual = output / 'visual/receipts'
    for state in ('open','submitted','qualified','private','qualification-failed','missing','late','incomplete-batch'):
        for width in (390,768,1280,1440):
            if not (visual / f'{state}-{width}.png').exists():
                raise ValueError('Receipt viewport evidence missing')
    qualified = read_json(visual / 'qualified-api.json')['receipt']
    if qualified['status'] != 'qualified' or qualified['job']['status'] != 'succeeded':
        raise ValueError('Actual compiled receipt missing')
    incomplete = read_json(visual / 'incomplete-batch-api.json')
    batch = incomplete['batch']
    if not 0 < batch['completed_matches'] < batch['expected_matches'] or batch['report']['status'] != 'incomplete' or incomplete['publication_response'] != 409:
        raise ValueError('Incomplete batch publication boundary missing')
    sources = ['.gitattributes','.gitignore','service/app.py','tests/test_receipts.py',
               'web/src/Receipts.tsx','web/src/Manage.tsx','web/src/Entrants.tsx','web/src/App.tsx',
               'web/src/pages.tsx','web/src/style.css','web/tests/receipts.spec.ts','tools/archive_receipt_evidence.py']
    paths = sorted(set(p for pattern in ('checks/*receipts*','visual/receipts/*','visual/receipts-regression/*.png')
                       for p in output.glob(pattern) if p.is_file() and p.name != 'receipts-stage.json'))
    archive = output / 'visual/receipts-evidence.zip'
    records = [dict(file=p.relative_to(output).as_posix(),bytes=p.stat().st_size,sha256=sha_file(p)) for p in paths]
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as zipped:
        for path, record in zip(paths,records):
            zipped.write(path,record['file'])
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() is not None:
            raise ValueError('Evidence CRC failed')
    write_json(checks / 'receipts-stage.json',dict(
        scope='C01/C02/C06 receipt, source and incomplete-ranking boundaries; partial A05; not final human aesthetics or complete accessibility',
        sources_sha256={name:sha_file(ROOT/name) for name in sources},
        build_sha256={p.relative_to(ROOT).as_posix():sha_file(p) for p in (ROOT/'web/dist').rglob('*') if p.is_file()},
        python_tests=78,browser=reports,receipt_screenshots=32,
        regression_screenshots=len(list((output/'visual/receipts-regression').glob('*.png'))),
        archive=dict(file=archive.relative_to(output).as_posix(),bytes=archive.stat().st_size,sha256=sha_file(archive),files=records),
        diagnostics=dict(initial_python='Actual compiler execution denied in sandbox; all six affected checks passed in escalated full regression.',
            initial_browser='Two selector mismatches; actual failed JSON retained. Initial raw log was overwritten after a wrong-relative-path copy failed; not claimed as retained.',
            boundary_runs='Wrong button label, then a queued job exceeded the 20-second start expectation while a prior 100-match fixture was running. Failure logs/JSON retained; fixture stopped through owner API, final case rerun independently.'),
        commands=[
            dict(command='python -m unittest discover -s tests -v',cwd='.',exit_code=0,log='checks/python-receipts.log'),
            dict(command='npm.cmd run build',cwd='web',exit_code=0,log='checks/build-receipts.log'),
            dict(command='npm.cmd test -- tests/receipts.spec.ts tests/workflows.spec.ts',cwd='web',exit_code=0,report='checks/browser-receipts.json'),
            dict(command="npm.cmd test -- tests/receipts.spec.ts -g 'unfinished batch'",cwd='web',exit_code=0,report='checks/browser-receipts-boundary.json'),
            dict(command='npm.cmd test -- tests/states.spec.ts tests/spectator.spec.ts tests/evidence.spec.ts tests/zz_recovery.spec.ts',cwd='web',exit_code=0,report='checks/browser-receipts-regression.json')],
        environment=dict(ARENA_BASE_URL='http://127.0.0.1:8851',ARENA_EMPTY_URL='http://127.0.0.1:8852',
            data='artifacts/work/v0.2-receipts-01',empty_data='artifacts/work/v0.2-receipts-empty-01'),
        reviewer=dict(name='Codex',final_human_aesthetic=False)))
    print(json.dumps(dict(files=len(records),archive_sha256=sha_file(archive),bytes=archive.stat().st_size)))


if __name__ == '__main__':
    main()
