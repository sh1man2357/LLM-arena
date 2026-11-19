"""Publish both public task ZIPs for Vite's dev server and production build."""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.build_devkit import package


def main():
    public = ROOT / "web/public/devkits"
    public.mkdir(parents=True, exist_ok=True)
    work = ROOT / "artifacts/work"
    work.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=work, prefix="web-devkits-") as directory:
        # Keep compiler scratch files with the build, including on Windows.
        for key in ("TEMP", "TMP", "TMPDIR"):
            os.environ[key] = directory
        for game, filename in (("bomberman", "llm-arena-devkit.zip"),
                               ("gomoku", "llm-arena-gomoku-devkit.zip")):
            archive = Path(directory) / filename
            package(archive, game)
            archive.replace(public / filename)


if __name__ == "__main__":
    main()
