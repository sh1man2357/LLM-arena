"""Run documented commands in an independently provisioned checkout."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.io import write_json, read_json


def main():
    p = argparse.ArgumentParser(); p.add_argument("directory"); p.add_argument("--output", required=True)
    p.add_argument("--reference-entrants", required=True)
    args = p.parse_args(); folder = Path(args.directory).resolve()
    python = str(folder / ".venv/Scripts/python.exe")
    commands = [[python, "--version"], [python, "-m", "pip", "list", "--format=json"],
                [python, "arena.py", "--help"],
                [python, "arena.py", "build", "sdk/template.cpp", "--output", "artifacts/work/template.wasm"],
                [python, "arena.py", "qualify", "artifacts/work/template.wasm"],
                [python, "arena.py", "baselines", "--output", "artifacts/work/baselines"],
                [python, "arena.py", "match", "--bot", "heuristic=artifacts/work/baselines/heuristic.wasm",
                 "--bot", "random=artifacts/work/baselines/random.wasm", "--map-seed", "1",
                 "--bot-seed", "0000000000000001", "--bot-seed", "0000000000000002", "--output", "artifacts/work/example"],
                [python, "arena.py", "view", "artifacts/work/example/replay.jsonl", "--output", "artifacts/work/example/replay.txt"],
                [python, "arena.py", "verify", "artifacts/work/example/replay.jsonl"],
                [python, "arena.py", "verify", "artifacts/work/example/replay.jsonl",
                 "--wasm", "artifacts/work/baselines/heuristic.wasm", "--wasm", "artifacts/work/baselines/random.wasm"],
                [python, "arena.py", "tournament", "--entrants", "artifacts/work/baselines/entrants.json",
                 "--cases", "configs/acceptance-cases.json", "--output", "artifacts/acceptance/clean-room"],
                [python, "arena.py", "verify-all", "artifacts/acceptance/clean-room", "--entrants",
                 "artifacts/work/baselines/entrants.json", "--rerun"]]
    logs = []
    try:
        for i, command in enumerate(commands):
            print(f"Clean-room command {i+1}/{len(commands)}: {' '.join(command[1:3])}", flush=True)
            result = subprocess.run(command, cwd=folder, capture_output=True, text=True, encoding="utf-8", timeout=180)
            logs.append(dict(command=command, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
            if result.returncode: raise ValueError(result.stderr or result.stdout)
        expected = {Path(e["wasm"]).stem: read_json(Path(e["wasm"]).with_suffix(".metadata.json"))["wasm_sha256"]
                    for e in read_json(args.reference_entrants)}
        actual = {name: read_json(folder / f"artifacts/work/baselines/{name}.metadata.json")["wasm_sha256"]
                  for name in expected}
        if actual != expected: raise ValueError("Clean checkout compiled different Baseline artifacts")
        proof = dict(status="passed", directory=str(folder), platform=platform.platform(), commands=logs,
                     baseline_hashes=actual, template_qualified=True, matches=300, bot_rerun=True)
    except Exception as exc:
        proof = dict(status="failed", directory=str(folder), diagnostic=str(exc), commands=logs)
        write_json(args.output, proof); raise
    write_json(args.output, proof)
    print(dict(status="passed", commands=len(logs), matches=300))


if __name__ == "__main__": main()
