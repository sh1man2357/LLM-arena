"""Generate the current public reference fixture used by browser checks."""
from pathlib import Path
import sys
import argparse
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from service.reference import reference_archive

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chain-output')
    args = parser.parse_args()
    archive = reference_archive()
    if args.chain_output:
        path = Path(args.chain_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as source:
            path.write_bytes(source.read('examples/chain/replay.jsonl'))
    print(archive)
