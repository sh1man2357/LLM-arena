"""Validate page-state evidence and preserve actual reports/media with provenance."""
import json
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.io import ROOT, read_json, write_json, sha_file


def passed_report(path, count):
    report = read_json(path)
    stats = report['stats']
    if stats['expected'] != count or any(stats[k] for k in ('unexpected', 'skipped', 'flaky')) or report['errors']:
        raise ValueError(f'Incomplete browser proof: {path}')
    return stats


def main():
    output = ROOT / 'artifacts/acceptance/v0.2-development'
    checks = output / 'checks'
    final = passed_report(checks / 'browser-read-states-final.json', 20)
    design = passed_report(checks / 'browser-read-states-design.json', 1)
    full_log = (checks / 'browser-read-states-regression.log').read_text(encoding='utf-8')
    if not re.search(r'26 passed', full_log) or set(map(int, re.findall(r'(?m)^\s+ok\s+(\d+)\s+tests', full_log))) != set(range(1, 27)):
        raise ValueError('All 26 actual full-run cases must have passing log records')
    visual = output / 'visual/read-states-final'
    for page in ('hall', 'viewer', 'batch', 'entrants', 'entrant', 'manage'):
        for width in (390, 768, 1280, 1440):
            if not (visual / f'{page}-normal-{width}.png').exists():
                raise ValueError('Missing real normal-page viewport coverage')
    for page in ('hall', 'viewer', 'batch', 'entrants', 'batches', 'manage'):
        for state in ('loading', 'unavailable'):
            for width in (390, 768, 1280, 1440):
                if not (visual / f'{page}-{state}-{width}.png').exists():
                    raise ValueError('Missing read-state viewport coverage')
    views = read_json(checks / 'read-states-visual-review.json')
    if views['status'] != 'captured' or len(views['screenshots']) != 10 or views['page_errors']:
        raise ValueError('Viewport review incomplete')
    for view in views['screenshots']:
        if sha_file(visual / view['file']) != view['sha256']:
            raise ValueError('Viewport media changed')
    performance = read_json(output / 'read-states-regression/checks/performance-final.json')
    if performance['status'] != 'passed' or performance['page_errors'] or len(performance['navigations']) != 12 or len(performance['seeks']) != 144 or len(performance['animations']) != 4:
        raise ValueError('Current frontend performance regression incomplete')
    if any(n['first_paint_ms'] > 1500 for n in performance['navigations']) or any(s['latency_ms'] > 100 for s in performance['seeks']):
        raise ValueError('Current paint/seek regression failed')
    if any(a['canvas_animation_fps'] < 55 or a['player0_interpolation_reversals'] for a in performance['animations']):
        raise ValueError('Current playback regression failed')
    sources = ['.gitattributes', '.gitignore', 'web/src/api.ts', 'web/src/ui.tsx', 'web/src/Hall.tsx',
               'web/src/Batch.tsx', 'web/src/Entrants.tsx', 'web/src/Manage.tsx', 'web/src/Viewer.tsx',
               'web/src/style.css', 'web/src/Board.tsx', 'web/src/tokens.css', 'web/playwright.config.ts',
               'web/tests/states.spec.ts', 'web/tools/capture-page-views.mjs', 'tools/archive_read_states.py']
    paths = sorted(set(p for pattern in ('checks/*read-states*', 'visual/read-states/*.png',
                   'visual/read-states-final/*.png', 'read-states-regression/checks/*')
                   for p in output.glob(pattern) if p.is_file() and p.name != 'read-states-stage.json'))
    archive = output / 'visual/read-states-evidence.zip'
    records = [dict(file=p.relative_to(output).as_posix(), bytes=p.stat().st_size, sha256=sha_file(p)) for p in paths]
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for path, record in zip(paths, records):
            zipped.write(path, record['file'])
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() is not None:
            raise ValueError('Archive CRC failed')
    write_json(checks / 'read-states-stage.json', dict(
        scope='A01 shared design/pages; partial A04/A05 read-state coverage, not complete accessibility or human aesthetics',
        source_files_sha256={name: sha_file(ROOT / name) for name in sources},
        build_files_sha256={p.relative_to(ROOT).as_posix(): sha_file(p) for p in (ROOT / 'web/dist').rglob('*') if p.is_file()},
        browser=dict(full_run_before_final_layout=dict(passed=26, evidence='checks/browser-read-states-regression.log',
            source_provenance='checks/read-states-before-refinement.json', json_retained=False),
            final_states=final, final_design=design,
            diagnostic_limitations='checks/read-states-diagnostics.json'),
        performance=dict(file='read-states-regression/checks/performance-final.json', summary=performance['summary'],
            normal_canvas_fps=[a['canvas_animation_fps'] for a in performance['animations']]),
        visual_review=dict(reviewer='Codex', final_human_aesthetic=False, normal_page_families=5,
            full_page_screenshots=len(list(visual.glob('*.png'))) - 11, viewport_views=10,
            premature_preview_view_retained='visual/read-states-final/hall-preview-loading-viewport-390.png'),
        archive=dict(file=archive.relative_to(output).as_posix(), bytes=archive.stat().st_size, sha256=sha_file(archive), files=records),
        commands=[
            dict(command='python tools/prepare_performance_checks.py --data artifacts/work/v0.2-read-states-01 --proof artifacts/acceptance/v0.2-development/checks/read-states-fixture.json', cwd='.', exit_code=0),
            dict(command='npm.cmd run build', cwd='web', exit_code=0, log='checks/build-read-states-final.log'),
            dict(command='npm.cmd test', cwd='web', exit_code=0, environment=dict(ARENA_BASE_URL='http://127.0.0.1:8841', ARENA_EMPTY_URL='http://127.0.0.1:8842'), log='checks/browser-read-states-regression.log', phase='before final compact error/countdown refinements'),
            dict(command='npm.cmd test -- tests/states.spec.ts', cwd='web', exit_code=0, environment=dict(ARENA_BASE_URL='http://127.0.0.1:8841', ARENA_EMPTY_URL='http://127.0.0.1:8842', ARENA_STATE_EVIDENCE='../artifacts/acceptance/v0.2-development/visual/read-states-final'), report='checks/browser-read-states-final.json', report_saved='copied actual test-results/results.json before any subsequent run'),
            dict(command="npm.cmd test -- tests/states.spec.ts -g 'five page families'", cwd='web', exit_code=0, environment=dict(ARENA_BASE_URL='http://127.0.0.1:8841', ARENA_STATE_EVIDENCE='../artifacts/acceptance/v0.2-development/visual/read-states-final', ARENA_BROWSER_RESULTS='../artifacts/acceptance/v0.2-development/checks/browser-read-states-design.json')),
            dict(command='node tools/capture-page-views.mjs http://127.0.0.1:8841 ../artifacts/acceptance/v0.2-development', cwd='web', exit_code=0),
            dict(command="& ./tools/capture_performance_machine.ps1 -Output artifacts/acceptance/v0.2-development/read-states-regression/checks/performance-machine.json -Node 'C:\\syn-D\\nodejs\\node.exe'", cwd='.', exit_code=0),
            dict(command='node tools/measure-performance.mjs http://127.0.0.1:8841 ../artifacts/acceptance/v0.2-development/read-states-regression final', cwd='web', exit_code=0),
        ]))
    print(json.dumps(dict(archive=str(archive.relative_to(ROOT)), files=len(records), bytes=archive.stat().st_size,
        sha256=sha_file(archive), final_screenshots=len(list(visual.glob('*.png')))), ensure_ascii=False))


if __name__ == '__main__':
    main()
