"""Probe the local development environment without traceback on missing tools."""
import importlib.metadata
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    try:
        from runner.compiler import compiler_path
        if sys.version_info[:2] != (3, 12):
            raise ValueError('Python 3.12 required')
        if importlib.metadata.version('wasmtime') != '49.0.0':
            raise ValueError('Wasmtime 49.0.0 required')
        compiler_path()
    except (ImportError, OSError, ValueError) as exc:
        print(f'Environment needs setup: {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
