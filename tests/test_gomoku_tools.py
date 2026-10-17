from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import hashlib

from runner.cli import parser, execute
from runner.compiler import compiler_path, compile_bot
from runner.io import ROOT, read_json, write_json, sha_file
from replay.verify import read, verify_world
from runtime.wasm import Backend
from runner.match import qualify
from tools.gomoku_practice import practice
from tools.build_devkit import package
from tests.test_runtime import module


class GomokuToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.a = self.root / "a.wasm"; self.a.write_bytes(module("i32.const 112"))
        self.b = self.root / "b.wasm"; self.b.write_bytes(module("i32.const 225"))

    def tearDown(self):
        self.temp.cleanup()

    def test_cli_pair_and_auto_detected_verify_view(self):
        out = self.root / "pair"
        args = parser().parse_args(["match", "--game", "gomoku", "--bot", f"a={self.a}", "--bot", f"b={self.b}",
                                    "--map-seed", "4", "--opening-mode", "library", "--output", str(out)])
        result = execute(args)
        self.assertTrue(result["valid"])
        self.assertEqual(result["score"], [1, 1])
        first, swapped = [read(out / f"replay-{side}.jsonl") for side in ("first", "swap")]
        self.assertEqual(first[0]["bot_seeds"], swapped[0]["bot_seeds"][::-1])
        self.assertEqual(first[0]["map"], swapped[0]["map"])
        for records in (first, swapped): verify_world(records)
        self.assertEqual(execute(parser().parse_args(["verify", str(out / "replay-first.jsonl")]))["status"], "verified")
        text = self.root / "view.txt"
        execute(parser().parse_args(["view", str(out / "replay-first.jsonl"), "--output", str(text)]))
        self.assertIn("ply 3", text.read_text()); self.assertIn("result:", text.read_text())
        with self.assertRaises(ValueError): execute(args)

    def test_practice_frozen_baselines_pairing_and_hashes(self):
        write_json(self.root / "configs/gomoku-public-dev.json", read_json(ROOT / "configs/gomoku-public-dev.json"))
        files = {}
        for name in ("baseline",):
            p = self.root / f"bots/gomoku/{name}.wasm"; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(self.b.read_bytes())
            files[p.relative_to(self.root).as_posix()] = dict(sha256=sha_file(p))
        write_json(self.root / "devkit-manifest.json", dict(game_id="gomoku", files=files))
        with patch("tools.gomoku_practice.ROOT", self.root):
            summary = practice(None, self.a, self.root / "practice", ("baseline",), 1)
            self.assertEqual(summary["matches"], 2)
            self.assertEqual(summary["mean_placement"], .5)
            self.assertEqual(summary['rating'],0)
            self.assertEqual(summary['reference_rating'],0)
            for name in ("baseline",):
                first, swapped = [read(self.root / f"practice/replays/{name}-00-{side}.jsonl") for side in ("first", "swap")]
                self.assertEqual(first[0]["bot_seeds"], swapped[0]["bot_seeds"][::-1])
                verify_world(first); verify_world(swapped)
            p = self.root / "bots/gomoku/baseline.wasm"; p.write_bytes(p.read_bytes()+b"changed")
            with self.assertRaisesRegex(ValueError, "frozen devkit"):
                practice(None, self.a, self.root / "changed", ("baseline",), 1)
            for players in (1, 3, True):
                with self.assertRaisesRegex(ValueError, "two players"):
                    practice(None, self.a, self.root / "invalid", ("baseline",), 1, players)

    def test_public_package_root_entrypoint_manifest_and_real_sdk(self):
        path = self.root / "gomoku.zip"
        package(path, "gomoku")
        extracted = self.root / "unpacked"
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            for name in ("README.md", "START_HERE.md", "MODEL_TASK.md", "start-devkit.ps1", "arena.py",
                         "LICENSE", "THIRD_PARTY_NOTICES.md", "licenses/musl-COPYRIGHT.txt", "tools/python-runtime.ps1"):
                self.assertIn(name, names)
            self.assertFalse(any(n.startswith(("artifacts/", ".venv/", ".tools/", "service/")) for n in names))
            z.extractall(extracted)
        manifest = read_json(extracted / "devkit-manifest.json")
        self.assertEqual(set(manifest['qualifications']),{'baseline'})
        self.assertEqual(manifest['reference_rating'],0)
        self.assertEqual(manifest['version'],5)
        self.assertEqual(manifest["game_id"], "gomoku"); self.assertEqual(manifest["public_cases"], 12)
        for name, row in manifest["files"].items():
            data = (extracted / name).read_bytes()
            self.assertEqual(len(data), row["bytes"]); self.assertEqual(hashlib.sha256(data).hexdigest(), row["sha256"])
        self.assertIn((extracted / "sdk/gomoku/gomoku.hpp").read_text(encoding="utf-8"), (extracted / "MODEL_TASK.md").read_text(encoding="utf-8"))
        compiler = compiler_path()
        with patch("runner.compiler.ROOT", extracted), patch("runner.compiler.compiler_path", return_value=compiler):
            wasm = self.root / "extracted-template.wasm"
            compile_bot(extracted / "sdk/gomoku/template.cpp", wasm, "gomoku")
        with Backend() as b: qualify(b, wasm, "gomoku")
        with self.assertRaises(ValueError): package(path, "gomoku")
