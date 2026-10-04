"""Run the actual test suite and persist its command, environment and diagnostics."""
import argparse
from pathlib import Path
import platform
import re
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.io import ROOT, write_json


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", required=True)
    args = parser.parse_args()
    command = [sys.executable, "-m", "unittest", "discover", "-v"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    count = re.search(r"Ran (\d+) tests?", result.stderr)
    proof = dict(command=command, cwd=str(ROOT), exit_code=result.returncode,
                 python=sys.version, platform=platform.platform(),
                 test_count=int(count.group(1)) if count else None, stdout=result.stdout, stderr=result.stderr)
    write_json(args.output, proof)
    print(result.stdout); print(result.stderr)
    raise SystemExit(result.returncode)


if __name__ == "__main__": main()
