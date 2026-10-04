import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.compiler import compile_bot

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    args = parser.parse_args()
    try:
        result = compile_bot(args.source, args.output)
        print(result["wasm_sha256"])
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")
