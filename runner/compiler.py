import subprocess
import shlex
from pathlib import Path
from runner.io import ROOT, read_json, write_json, sha_file

FLAGS = ["-std=c++20", "-O2", "-fno-exceptions", "-fno-rtti", "-nostartfiles",
         "-mno-simd128", "-mno-reference-types", "-mno-tail-call",
         "-Wl,--no-entry", "-Wl,-z,stack-size=1048576", "-Wl,--max-memory=67108864",
         "-Wl,--export=arena_init", "-Wl,--export=arena_input_ptr", "-Wl,--export=arena_tick",
         "-Wl,--export-memory", "-Wl,--strip-all", "-Wl,--compress-relocations"]


def compiler_path():
    lock = read_json(ROOT / "configs/toolchain.json")
    compiler = ROOT / ".tools" / lock["archive"].removesuffix(".tar.gz") / "bin/clang++.exe"
    if not compiler.is_file():
        raise ValueError("Compiler missing; run python tools/bootstrap.py first")
    return compiler


def compile_bot(source, output, game_id="bomberman"):
    if game_id not in ("bomberman", "gomoku"):
        raise ValueError("Unknown game")
    sdk = ROOT / "sdk" / "gomoku" if game_id == "gomoku" else ROOT / "sdk"
    header = "gomoku.hpp" if game_id == "gomoku" else "arena.hpp"
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file() or source.stat().st_size > 1024 * 1024:
        raise ValueError("Bot source must exist and be <= 1 MiB")
    output.parent.mkdir(parents=True, exist_ok=True)
    compiler = compiler_path()
    command = [str(compiler), *FLAGS, "-I", str(sdk), str(sdk / "wrapper.cpp"),
               str(source), "-MMD", "-MF", str(output.with_suffix(".deps")),
               "-o", str(output.with_suffix(".tmp.wasm"))]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=60)
    log = dict(command=command, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
    write_json(output.with_suffix(".compile.json"), log)
    if result.returncode:
        raise ValueError(f"Compilation failed: {result.stderr}")
    output.with_suffix(".tmp.wasm").replace(output)
    if output.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("WASM exceeds 8 MiB eligibility cap")
    version = subprocess.run([str(compiler), "--version"], capture_output=True, text=True, timeout=10).stdout
    dependencies = {}
    dep_text = output.with_suffix(".deps").read_text(encoding="utf-8").replace("\\\n", " ")
    # Clang's Make dependencies keep native backslashes, but escape spaces.
    for dep in shlex.split(dep_text.split(": ", 1)[1].replace("\\", "/").replace("/ ", "\\ ")):
        path = Path(dep)
        if path.is_file():
            dependencies[str(path.resolve())] = sha_file(path)
    metadata = dict(source=str(source), source_sha256=sha_file(source), wasm_sha256=sha_file(output),
                    sdk_sha256={name: sha_file(sdk / name) for name in (header, "wrapper.cpp")},
                    compiler_version=version.strip(), compiler_sha256=sha_file(compiler), flags=FLAGS,
                    dependencies=dependencies, wasm=str(output), toolchain=read_json(ROOT / "configs/toolchain.json"))
    write_json(output.with_suffix(".metadata.json"), metadata)
    return metadata
