"""Archive rendered reports and the reproducible public engineering fault batch."""
import argparse
from pathlib import Path
import platform
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runner.io import ROOT,read_json,write_json,sha_file


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data',required=True)
    parser.add_argument('--output',default='artifacts/acceptance/v0.2-development');args=parser.parse_args()
    output=Path(args.output).resolve();proof=read_json(output/'checks/browser-report-quality.json')
    if proof['status']!='passed' or proof['page_errors']:raise ValueError('Report browser check must pass')
    regression=read_json(output/'checks/browser-analysis-regression.json')
    if regression['stats']['expected']!=8 or regression['stats']['unexpected']:raise ValueError('Full browser regression must pass')
    images=[]
    for name in proof['screenshots']:
        if Path(name).name!=name:raise ValueError('Only local image names are supported')
        path=output/'visual/report-quality'/name
        images.append(dict(file=name,bytes=path.stat().st_size,sha256=sha_file(path)))
    fault=Path(args.data).resolve()/'fault-tie'; archive=output/'visual/report-quality.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as target:
        for image in images:target.write(output/'visual/report-quality'/image['file'],f"visual/{image['file']}")
        for path in sorted(fault.rglob('*')):
            if path.is_file():target.write(path,'engineering-fault-tie/'+path.relative_to(fault).as_posix())
        for name in ['report-traces.json','browser-report-quality.json','browser-analysis-regression.json','python-analysis.log','python-analysis-final.log']:
            target.write(output/'checks'/name,'checks/'+name)
    with zipfile.ZipFile(archive) as target:
        if target.testzip() is not None:raise ValueError('Archive failed CRC check')
    sources=['service/analysis.py','service/app.py','service/imports.py','tests/test_analysis.py','tests/test_service.py',
             'web/src/Batch.tsx','web/src/style.css','tools/prepare_report_checks.py',
             'tools/archive_report_evidence.py','web/tools/verify-report-quality.mjs','web/tools/check-contrast.mjs']
    write_json(output/'checks/report-stage.json',dict(platform=platform.platform(),python=sys.version,browser=proof['browser'],
        source_files_sha256={name:sha_file(ROOT/name) for name in sources},
        checks_sha256={name:sha_file(output/'checks'/name) for name in ['report-traces.json','browser-report-quality.json','browser-analysis-regression.json','python-analysis.log','python-analysis-final.log']},
        archive=dict(file='visual/report-quality.zip',sha256=sha_file(archive),bytes=archive.stat().st_size,images=images),
        evidence_sources={name:sha_file(ROOT/name) for name in ['artifacts/acceptance/v0.1-release/evidence.zip','artifacts/acceptance/v0.2-baselines/evidence.zip']},
        commands=[dict(command='python tools/prepare_report_checks.py --data artifacts/work/v0.2-report-check-01 --proof artifacts/acceptance/v0.2-development/checks/report-traces.json',cwd='.',exit_code=0),
                  dict(command='python -m unittest discover -s tests -v',cwd='.',exit_code=0),
                  dict(command='python -m unittest tests.test_analysis tests.test_service -v',cwd='.',exit_code=0),
                  dict(command='npm.cmd run build',cwd='web',exit_code=0),
                  dict(command='npm.cmd test',cwd='web',environment=dict(ARENA_BASE_URL='http://127.0.0.1:8800'),exit_code=0),
                  dict(command='node tools/verify-report-quality.mjs',cwd='web',exit_code=0)]))
    print(f'Packaged {len(images)} report screenshots, public engineering traces and check logs with hashes.')


if __name__=='__main__':main()
