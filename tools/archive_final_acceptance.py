"""Audit explicit v0.2 requirements and seal evidence; never invent human approval."""
import json
from pathlib import Path
import re
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runner.io import ROOT,read_json,write_json,sha_file

def browser(path,count):
    d=read_json(path);s=d['stats']
    assert s['expected']==count and not any(s[k] for k in ('unexpected','skipped','flaky')) and not d['errors'],path
    return s

def main():
    root=ROOT/'artifacts/acceptance/v0.2-development';out=root/'final';checks=out/'checks'
    runs={'full_browser':browser(root/'checks/final-browser.json',34),'extra_compiling_state':browser(root/'checks/final-queue-browser.json',1)}
    assert re.search(r'Ran 81 tests in [\d.]+s\s+OK\s*$',(root/'checks/final-python.log').read_text(encoding='utf-8'))
    protocol=(root/'checks/final-protocol.log').read_text(encoding='utf-8')
    assert re.search(r'(?m)^.* pass 4\s*$',protocol) and re.search(r'(?m)^.* fail 0\s*$',protocol)
    access=read_json(checks/'accessibility.json');assert access['status']=='passed' and len(access['reports'])==24 and not access['page_errors']
    assert all(not r['violations'] and not r['small_controls'] and not r['unnamed'] and not r['overflow'] for r in access['reports'])
    for width in (390,768,1280,1440):assert '正在读取参赛对局' not in (out/f'visual/entrant-{width}-accessibility.txt').read_text(encoding='utf-8')
    assert access['keyboard']['space_toggles'] and access['keyboard']['input_does_not_seek']
    viewer=read_json(checks/'viewer-quality.json');assert viewer['status']=='passed' and len(viewer['checks'])==14 and len(viewer['screenshots'])==42 and not viewer['page_errors']
    for name in viewer['screenshots']+[viewer['video']]:assert (out/'visual/viewer-quality'/name).is_file()
    for name in ('queued-receipt-1280.png','compiling-receipt-1280.png'):assert (out/'visual'/name).is_file()
    perf=read_json(checks/'performance-final.json');assert perf['status']=='passed' and len(perf['navigations'])==12 and len(perf['seeks'])==144 and len(perf['animations'])==4
    assert not perf['page_errors'] and max(r['first_paint_ms'] for r in perf['navigations'])<=1500 and max(r['latency_ms'] for r in perf['seeks'])<=100
    assert all(r['canvas_animation_fps']>=55 and isinstance(r['player0_interpolation_reversals'],list) and not r['player0_interpolation_reversals'] for r in perf['animations'])
    assert read_json(checks/'runtime-frozen.json')['status']=='passed'
    review=read_json(checks/'review-viewport.json');assert review['status']=='captured' and len(review['screenshots'])==24 and not review['page_errors']
    assert review['human_approval'] is False
    for shot in review['screenshots']:assert sha_file(out/'visual/review-viewport'/shot['file'])==shot['sha256']
    assert 'Verified 29 documents' in (root/'checks/final-docs.log').read_text(encoding='utf-8')
    assert read_json(root/'checks/final-services.json')['status']=='passed'
    manifest=read_json(ROOT/'artifacts/acceptance/v0.2-baselines/manifest.json')
    core=manifest['components']['source_files'];assert len(core)==27 and all(sha_file(ROOT/n)==h for n,h in core.items())
    old={name:sha_file(ROOT/name) for name in ['artifacts/acceptance/v0.1-release/evidence.zip','artifacts/acceptance/v0.2-baselines/evidence.zip']}
    for archive in old:
        with zipfile.ZipFile(ROOT/archive) as z:assert z.testzip() is None
    reference=read_json(root/'checks/reference-300.json');assert reference['status']=='passed' and reference['matches']==300
    for name in ('live-process-recovery.json','recovery.json','clean-room-ui.json'):
        assert read_json(root/'checks'/name)['status']=='passed',name
    # Each row is an explicitly retained requirement; evidence is scoped rather than inferred from a green total.
    evidence={
        'A01':['checks/read-states-stage.json','docs/records/components-and-page-states.md'],
        'A02':['final/checks/viewer-quality.json'],'A03':['final/checks/viewer-quality.json'],
        'A04':['final/checks/accessibility.json','final/checks/viewer-quality.json'],
        'A05':['checks/final-browser.json','checks/final-queue-browser.json','docs/records/final-engineering-acceptance.md','checks/browser-live-recovery.json'],
        'A06':['docs/records/final-visual-review.md'],
        'B01':['final/checks/viewer-cases.json','final/checks/viewer-quality.json'],
        'B02':['final/checks/viewer-cases.json','final/checks/viewer-quality.json'],
        'B03':['checks/live-process-recovery.json'],'B04':['checks/browser-live-recovery.json','checks/live-process-recovery.json'],
        'B05':['final/checks/viewer-cases.json','final/checks/viewer-quality.json'],
        'C01':['checks/receipts-stage.json','checks/final-browser.json'],'C02':['checks/receipts-stage.json','checks/final-python.log','checks/final-browser.json'],
        'C03':['final/checks/runtime-api.json','final/checks/runtime-frozen.json','checks/final-python.log'],
        'C04':['checks/performance-stage.json'],'C05':['checks/live-stage.json','checks/final-python.log'],
        'C06':['checks/final-browser.json','checks/receipts-stage.json'],
        'D01':['artifacts/acceptance/v0.2-baselines/handoff.md','artifacts/acceptance/v0.2-baselines/evidence.zip'],
        'D02':['checks/report-stage.json','checks/report-traces.json'],'D03':['checks/legacy-import-publication.json','checks/final-browser.json'],
        'D04':['checks/reference-300.json'],'D05':['final/checks/runtime-api.json','checks/final-python.log'],
        'D06':['checks/final-browser.json','checks/browser-recovery-restored.json'],'D07':['checks/report-traces.json','docs/records/results-analysis.md'],
        'E01':['checks/final-python.log','checks/final-browser.json','service/__main__.py'],
        'E02':['checks/clean-room-ui.json'],'E03':['final/checks/performance-final.json','checks/performance-stage.json'],
        'E04':['checks/final-browser.json','checks/recovery.json'],'E05':['docs/releases/handoff-v0.2.md','docs/records/final-engineering-acceptance.md']}
    delivery=(ROOT/'docs/releases/v0.2.md').read_text(encoding='utf-8')
    items=re.findall(r'^- \[([ x])\] ([A-E]\d\d)：(.+)$',delivery,re.M)
    assert len(items)==29 and {i for _,i,_ in items}==set(evidence)
    pending=[i for status,i,_ in items if status==' ']
    assert pending in ([],['A06']),'Only the human visual gate may remain after engineering acceptance'
    passed=sum(status=='x' for status,_,_ in items)
    human=dict(status='pending',record='docs/records/final-visual-review.md',engineering_reviewer='Codex',human_reviewer=None)
    if not pending:
        approval=read_json(checks/'human-visual-approval.json')
        assert approval['status']=='approved' and approval['scope']=='A06'
        assert approval['source']=='direct_user_response' and approval['answer']=='通过视觉验收'
        assert approval['reviewer'] and approval['recorded_at'] and approval['question_reference']
        assert sha_file(ROOT/approval['review_record'])==approval['review_record_sha256']
        for name,checksum in approval['production_sources_sha256'].items():assert sha_file(ROOT/name)==checksum,name
        for media in approval['provided_media']:assert sha_file(ROOT/media['file'])==media['sha256'],media['file']
        evidence['A06'].append('final/checks/human-visual-approval.json')
        human.update(status='approved',human_reviewer=approval['reviewer'],recorded_at=approval['recorded_at'],
                     approval_record=(checks/'human-visual-approval.json').relative_to(ROOT).as_posix(),
                     approval_sha256=sha_file(checks/'human-visual-approval.json'))
    rows=[]
    for status,identity,requirement in items:
        sources=[]
        for name in evidence[identity]:
            file=ROOT/name if name.startswith(('docs/','artifacts/','service/')) else root/name
            assert file.is_file(),file
            sources.append(dict(file=file.relative_to(ROOT).as_posix(),sha256=sha_file(file)))
        rows.append(dict(id=identity,requirement=requirement,status='passed' if status=='x' else 'pending_human_visual_review',evidence=sources))
    paths=sorted(set(p for pattern in ('final/checks/*','final/visual/**/*','final/visual/*','checks/final*') for p in root.glob(pattern) if p.is_file()))
    records=[dict(file=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=sha_file(p)) for p in paths]
    archive=out/'evidence.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as zipped:
        for p,r in zip(paths,records):zipped.write(p,r['file'])
    with zipfile.ZipFile(archive) as zipped:assert zipped.testzip() is None
    sources=[p for pattern in ('web/src/*','web/tests/*.ts','web/tools/*.mjs','service/*.py','tests/*.py','tools/*.py') for p in ROOT.glob(pattern) if p.is_file()]
    write_json(out/'acceptance-index.json',dict(status='passed' if not pending else 'engineering_passed_awaiting_human_visual',passed=passed,total=29,requirements=rows,
        final_commands=[dict(command=c,cwd=cwd,exit_code=0,log=log) for c,cwd,log in [
            ('python -m unittest discover -s tests -v','.','checks/final-python.log'),('npm.cmd run test:protocol','web','checks/final-protocol.log'),
            ('npm.cmd run build','web','checks/final-build.log'),('npm.cmd test','web','checks/final-browser.log'),
            ("npm.cmd test -- tests/release.spec.ts -g 'actual FIFO'",'web','checks/final-queue-browser.log'),
            ('node tools/verify-viewer-quality.mjs http://127.0.0.1:8863 ../artifacts/acceptance/v0.2-development/final','web','checks/final-viewer-quality.log'),
            ('node tools/measure-performance.mjs http://127.0.0.1:8861 ../artifacts/acceptance/v0.2-development/final final','web','checks/final-performance.log'),
            ('node tools/audit-accessibility.mjs http://127.0.0.1:8861 ../artifacts/acceptance/v0.2-development/final','web','checks/final-accessibility.log'),
            ('node tools/capture-final-review.mjs http://127.0.0.1:8863 ../artifacts/acceptance/v0.2-development/final','web','checks/final-review-viewport.log'),
            ('python tools/check_docs.py','.','checks/final-docs.log')]],
        checks=dict(python=81,protocol=4,browser=runs,accessibility=dict(page_width_groups=24,text_instances=sum(len(r['text']) for r in access['reports']),controls=sum(len(r['controls']) for r in access['reports'])),viewer_groups=14,performance=perf['summary']),
        sources_sha256={p.relative_to(ROOT).as_posix():sha_file(p) for p in sources},
        build_sha256={p.relative_to(ROOT).as_posix():sha_file(p) for p in (ROOT/'web/dist').rglob('*') if p.is_file()},
        unchanged_core_sources_sha256=core,frozen_archives_sha256=old,
        archive=dict(file=archive.relative_to(ROOT).as_posix(),bytes=archive.stat().st_size,sha256=sha_file(archive),files=records),
        provenance=dict(native_data='artifacts/work/v0.2-final-viewer-01',workflow_data='artifacts/work/v0.2-final-01',empty_data='artifacts/work/v0.2-final-empty-01',
            reused='Baseline/compatibility/report/recovery/16MiB/install evidence retains its recorded code version; no new full 300-match claim.',
            full_browser='34 cases before extra compiling-state observation; unchanged production code, one final queue case rerun separately.'),
        diagnostics=['Initial accessibility selector mismatch; actual failure log retained.','Accessibility initially measured entrant metadata before match history loaded; initial JSON retained, final waits for actual full page reads.', 'Existing fixture directory refused; then native service was not yet ready. Initial missing-fixture response log overwritten; later not-ready log retained.',
            'Touch range was obscured by mobile navigation; actual UI repaired and native hit/drag rerun passed.','Long name pushed desktop controls out of viewport; two-line name display and actual viewport assertion passed.',
            'Release check posted before unlock, then expected an empty-name submit button to be enabled; both failed reports retained and corrected.',
            'Pre-name-refinement native/performance JSON retained; its full original media was overwritten, not claimed as separately preserved.'],
        human_visual=human))
    print(json.dumps(dict(passed=passed,total=29,archive_bytes=archive.stat().st_size,archive_sha256=sha_file(archive),files=len(paths))))

if __name__=='__main__':main()
