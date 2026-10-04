import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from fastapi.testclient import TestClient
from runner.io import ROOT
from service.app import create_app
from service.imports import import_replay, extract_archive
from service.replays import from_bytes


class SpectatorFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(ROOT / "artifacts/acceptance/v0.1-release/evidence.zip") as archive:
            cls.data = archive.read("examples/chain/replay.jsonl")

    def test_chain_projection_matches_real_geometry_without_private_seeds(self):
        ui = from_bytes(self.data)
        self.assertTrue(ui["verified"])
        self.assertEqual(ui["frames"][0]["state"]["tick"], 0)
        self.assertEqual(ui["frames"][-1]["tick"], 18)
        self.assertEqual(len(ui["frames"][-1]["visual"]["exploded_bombs"]), 2)
        self.assertEqual(sum(b["chain"] for b in ui["frames"][-1]["visual"]["exploded_bombs"]), 1)
        self.assertNotIn("map_seed", json.dumps(ui))
        self.assertNotIn("bot_seeds", json.dumps(ui))
        self.assertNotIn("source_files", json.dumps(ui))

    def test_corrupt_tick_and_unknown_schema_are_rejected(self):
        records = [json.loads(l) for l in self.data.decode().splitlines()]
        records[1]["state"]["players"][0]["x"] += 1
        with self.assertRaises(ValueError):
            from_bytes("\n".join(json.dumps(r) for r in records).encode())
        records[0]["schema_version"] = 9
        with self.assertRaises(ValueError):
            from_bytes("\n".join(json.dumps(r) for r in records).encode())

    def test_local_boundary_and_frozen_import(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(directory)
            row = import_replay(app.state.store, self.data)
            with TestClient(app) as client:
                response = client.get(f"/api/v1/matches/{row['id']}/frames")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.json()["frames"]), 20)
                self.assertEqual(client.post("/api/v1/imports").status_code, 403)
                self.assertEqual(client.get("/health", headers={"host": "evil.example"}).status_code, 403)
                self.assertEqual(client.post("/api/v1/admin/unlock", headers={"origin": "https://evil.example", "x-arena-local": "1"}).status_code, 403)
                self.assertEqual(client.post("/api/v1/admin/unlock", headers={"x-arena-local": "1"}).status_code, 200)
                self.assertEqual(client.post("/api/v1/imports", json={"source": "../../private"}).status_code, 422)
                content = client.get(f"/api/v1/exports/{row['id']}").json()
                self.assertNotIn("bot_seeds", json.dumps(content))
                self.assertNotIn("replay", client.get(f"/api/v1/matches/{row['id']}").json())

    def test_archive_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../escaped.txt", "bad")
            with self.assertRaises(ValueError):
                extract_archive(path, Path(directory) / "import")


if __name__ == "__main__":
    unittest.main()
