"""Install the frozen local compiler, without modifying system PATH."""
import hashlib
import argparse
import json
from pathlib import Path
import platform
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Install frozen Windows WASI SDK")
    parser.add_argument("--archive", help="Reuse a locally cached official archive (SHA-256 checked)")
    args = parser.parse_args()
    if platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise SystemExit("This toolchain lock is verified on Windows x64 only")
    lock = json.loads((ROOT / "configs/toolchain.json").read_text(encoding="utf-8"))
    tools = ROOT / ".tools"
    tools.mkdir(exist_ok=True)
    archive = Path(args.archive).resolve() if args.archive else tools / lock["archive"]
    if not archive.exists():
        partial = archive.with_suffix(".part")
        with urllib.request.urlopen(lock["url"], timeout=60) as source, partial.open("wb") as target:
            total = 0
            last = 0
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
                total += len(chunk)
                if total - last >= 64 * 1024 * 1024:
                    print(f"Downloaded {total // 1024 // 1024} MiB", flush=True)
                    last = total
        partial.replace(archive)
    with archive.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    if checksum != lock["sha256"]:
        raise SystemExit("Compiler archive checksum mismatch; remove the archive and retry")
    folder = tools / lock["archive"].removesuffix(".tar.gz")
    if not (folder / "bin/clang++.exe").exists():
        print("Extracting verified compiler archive", flush=True)
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(tools, filter="data")
    if not (folder / "bin/clang++.exe").exists():
        raise SystemExit("Compiler archive has an unexpected directory layout")
    print(f"Compiler ready: {folder / 'bin/clang++.exe'}", flush=True)


if __name__ == "__main__":
    main()
