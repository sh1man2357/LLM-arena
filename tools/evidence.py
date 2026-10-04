"""Archive raw acceptance evidence and verify it before restoring to a new directory."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.io import write_json, sha_file


def main():
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="command", required=True)
    pack = sub.add_parser("pack"); pack.add_argument("directory"); pack.add_argument("--output", required=True)
    restore = sub.add_parser("restore"); restore.add_argument("archive"); restore.add_argument("--output", required=True)
    restore.add_argument("--sha256", required=True)
    args = p.parse_args()
    if args.command == "pack":
        root, output = Path(args.directory).resolve(), Path(args.output).resolve()
        files = sorted(path for path in root.rglob("*") if path.is_file()
                       and path.resolve() != output and path.suffix not in (".zip", ".tmp")
                       and path.name != "evidence-index.json")
        index = {path.relative_to(root).as_posix(): sha_file(path) for path in files}
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for path in files: bundle.write(path, path.relative_to(root).as_posix())
            bundle.writestr("evidence-index.json", json.dumps(index, indent=2))
        proof = dict(archive=str(output), sha256=sha_file(output), files=len(index), bytes=output.stat().st_size)
        write_json(output.with_suffix(".index.json"), proof)
        print(proof)
    else:
        archive, output = Path(args.archive), Path(args.output).resolve()
        if sha_file(archive) != args.sha256: raise ValueError("Evidence archive SHA-256 mismatch")
        if output.exists(): raise ValueError("Restore requires a new output directory")
        with zipfile.ZipFile(archive) as bundle:
            if len(bundle.namelist()) != len(set(bundle.namelist())): raise ValueError("Duplicate ZIP entry")
            index = json.loads(bundle.read("evidence-index.json"))
            if set(bundle.namelist()) != set(index) | {"evidence-index.json"}: raise ValueError("ZIP index differs")
            for name, checksum in index.items():
                posix = PurePosixPath(name)
                target = (output / name).resolve()
                if posix.is_absolute() or ".." in posix.parts or not target.is_relative_to(output):
                    raise ValueError("Unsafe archive entry")
                data = bundle.read(name)
                if hashlib.sha256(data).hexdigest() != checksum: raise ValueError(f"Corrupt evidence: {name}")
                target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        print(dict(status="restored", files=len(index), output=str(output)))


if __name__ == "__main__": main()
