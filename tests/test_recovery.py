"""Portable private recovery and seed-free public Replay trust boundaries."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
from runner.io import ROOT, sha_file
from runner.match import components
from service.app import create_app
from service.backup import create_backup, restore_backup
from service.imports import import_replay, import_tournament
from service.jobs import Queue
from service.publication import close_submissions, publish_tournament, published_file
from service.replays import from_bytes
from service.store import Store
from service.submissions import create_session, submit
from tests.test_import_publication import fixture


def bytes_of(value):
    return json.dumps(value, ensure_ascii=False).encode()


class PublicReplayRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(ROOT / "artifacts/acceptance/v0.1-release/evidence.zip") as archive:
            cls.original = archive.read("examples/chain/replay.jsonl")

    def test_roundtrip_recomputes_world_and_keeps_distinct_file_origin_hashes(self):
        exported = from_bytes(self.original)
        exported["verified"] = False  # The flag does not decide acceptance.
        data = bytes_of(exported)
        imported = from_bytes(data)
        self.assertTrue(imported["verified"])
        self.assertEqual(imported["frames"], exported["frames"])
        self.assertEqual(imported["result"], exported["result"])
        self.assertEqual(imported["source_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(imported["origin_source_sha256"], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(imported["origin_association"], "unverified_claim")
        self.assertFalse(imported["bot_rerunnable"])
        again = from_bytes(bytes_of(imported))
        self.assertEqual(again["origin_source_sha256"], imported["origin_source_sha256"])
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            row = import_replay(store, data)
            self.assertEqual(row["source_format"], "public_projection")
            self.assertTrue(all(e["status"] == "historical" for e in store.list("entrant")))
            self.assertEqual(Path(row["replay"]).read_bytes(), data)

    def test_forged_flags_frames_geometry_results_and_incomplete_sources_fail(self):
        source = from_bytes(self.original)
        mutations = [lambda v: v["frames"][1]["state"]["players"][0].update(x=4),
                     lambda v: v["frames"][-1]["visual"]["coverage"].clear(),
                     lambda v: v["result"]["players"][0].update(placement_score=1),
                     lambda v: v["frames"][2].update(seq=3), lambda v: v.update(partial=True),
                     lambda v: v.update(projection_version=99),
                     lambda v: v["frames"][1]["calls"].append(v["frames"][1]["calls"][0])]
        for mutate in mutations:
            modified = deepcopy(source)
            mutate(modified)
            modified["verified"] = True
            with self.assertRaises(ValueError):
                from_bytes(bytes_of(modified))
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(directory)) as client:
                client.post("/api/v1/admin/unlock", headers={"x-arena-local": "1"})
                self.assertEqual(client.post("/api/v1/imports/replay", files={"file": ("bad.json", b'{"projection_version":1}')}).status_code, 422)


class PrivateBackupRecoveryTests(unittest.TestCase):
    def prepared(self, root, *, queued=True):
        fixture(root / "legacy")  # Includes artifacts outside the data directory.
        store = Store(root / "data")
        batch = import_tournament(store, root / "legacy", "portable-batch")
        close_submissions(store, batch["id"])
        batch = publish_tournament(store, batch["id"])
        session = create_session(store, "Frozen CPP", "engineering fixture")
        source = '#include "arena.hpp"\nnamespace bot { void init(uint64_t) {} Action tick(const GameState&) { return Action::WAIT; } }\n'
        submitted = submit(store, session["id"], source)
        queue = Queue(store)
        if queued:
            compile_job = queue.create("compile", dict(submission_id=submitted["id"], components=components()))
        else:
            compile_job = None
        return store, batch, session, submitted, compile_job

    def test_restore_preserves_private_evidence_rotates_credentials_and_resumes_frozen_job(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, batch, session, submitted, job = self.prepared(root)
            old_token = store.token
            archive = create_backup(store)
            destination = root / "restored"
            restored = restore_backup(archive["path"], destination, expected_sha256=archive["sha256"])
            self.assertEqual(restored["interrupted_jobs"], [job["id"]])
            fresh = Store(destination)
            self.assertNotEqual(fresh.token, old_token)
            self.assertEqual(fresh.get("session", session["id"]), store.get("session", session["id"]))
            new_submission = fresh.get("submission", submitted["id"])
            self.assertEqual(sha_file(new_submission["source"]), submitted["source_sha256"])
            self.assertTrue(Path(new_submission["source"]).is_relative_to(destination))
            restored_batch = fresh.get("tournament", batch["id"])
            for key in ("published_at", "publication_id", "publication_sha256", "window_closed_at", "window_closed_entrants", "report"):
                self.assertEqual(restored_batch[key], batch[key])
            self.assertEqual(published_file(fresh, restored_batch, "publication").read_bytes(), published_file(store, batch, "publication").read_bytes())
            self.assertEqual(len(fresh.list("match")), 2)
            self.assertEqual(fresh.events(), store.events())
            app = create_app(destination, workers=True)
            with TestClient(app) as client:
                client.cookies.set("arena_owner", old_token)
                self.assertEqual(client.get("/api/v1/submissions").status_code, 403)
                client.post("/api/v1/admin/unlock", headers={"x-arena-local": "1"})
                self.assertEqual(client.get(f"/api/v1/jobs/{job['id']}").json()["status"], "interrupted")
                self.assertEqual(client.post(f"/api/v1/jobs/{job['id']}/resume").status_code, 200)
                deadline = time.monotonic()+30
                while time.monotonic() < deadline:
                    finished = client.get(f"/api/v1/jobs/{job['id']}").json()
                    if finished["status"] in ("failed", "succeeded"):
                        break
                    time.sleep(.03)
                self.assertEqual(finished["status"], "succeeded", finished)
                self.assertEqual(client.get(f"/api/v1/submissions/{submitted['id']}").json()["status"], "qualified")

    def test_tampered_archive_and_existing_destination_never_replace_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, batch, *_ = self.prepared(root, queued=False)
            original = create_backup(store)
            path = Path(original["path"])
            with zipfile.ZipFile(path) as archive:
                entries = {i.filename: archive.read(i) for i in archive.infolist()}
            file_name = next(name for name in entries if name.endswith(".wasm"))
            entries[file_name] += b"changed"
            damaged = root / "damaged.zip"
            with zipfile.ZipFile(damaged, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, data in entries.items():
                    archive.writestr(name, data)
            destination = root / "target"
            with self.assertRaises(ValueError):
                restore_backup(damaged, destination)
            self.assertFalse(destination.exists())
            with self.assertRaises(ValueError):
                restore_backup(path, destination, expected_sha256="0"*64)
            self.assertFalse(destination.exists())
            destination.mkdir()
            sentinel = destination / "keep.txt"
            sentinel.write_text("existing data")
            with self.assertRaises(FileExistsError):
                restore_backup(path, destination)
            self.assertEqual(sentinel.read_text(), "existing data")
            self.assertEqual(store.get("tournament", batch["id"])["publication_sha256"], batch["publication_sha256"])

    def test_backup_path_reference_injection_and_traversal_fail_without_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, *_ = self.prepared(root, queued=False)
            original = create_backup(store)
            with zipfile.ZipFile(original["path"]) as archive:
                entries = {i.filename: archive.read(i) for i in archive.infolist()}
            for mode in ("reference", "traversal", "token"):
                changed = dict(entries)
                snapshot = json.loads(changed["snapshot.json"])
                if mode == "reference":
                    snapshot["references"][0]["archive_path"] = "../../outside"
                    changed["snapshot.json"] = bytes_of(snapshot)
                elif mode == "traversal":
                    changed["../outside"] = b"bad"
                else:
                    name, data = "data/owner.token", b"imported credentials"
                    changed[name] = data
                    snapshot["files"].append(dict(path=name, size=len(data), sha256=hashlib.sha256(data).hexdigest()))
                    changed["snapshot.json"] = bytes_of(snapshot)
                path = root / f"bad-{mode}.zip"
                with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                    for name, data in changed.items():
                        archive.writestr(name, data)
                with self.assertRaises(ValueError):
                    restore_backup(path, root / f"restore-{mode}")
                self.assertFalse((root / f"restore-{mode}").exists())
            self.assertFalse((root / "outside").exists())

    def test_changed_frozen_source_blocks_backup_and_caches_rebuild_from_raw_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, batch, session, submitted, _ = self.prepared(root, queued=False)
            source = Path(submitted["source"])
            original = source.read_bytes()
            source.write_bytes(original + b"changed")
            with self.assertRaises(ValueError):
                create_backup(store)
            self.assertEqual(store.list("backup"), [])
            source.write_bytes(original)
            row = store.list("match")[0]
            Path(row["projection"]).write_text("invalid derived cache")
            backup = create_backup(store)
            restore_backup(backup["path"], root / "restored")
            fresh = Store(root / "restored")
            rebuilt = json.loads(Path(fresh.get("match", row["id"])["projection"]).read_text(encoding="utf-8"))
            self.assertTrue(rebuilt["verified"])
            self.assertEqual(rebuilt["result"], row["result"])

    def test_async_private_backup_api_owner_boundary_and_live_workspace_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(root / "data", workers=True)
            with TestClient(app) as client:
                self.assertEqual(client.post("/api/v1/backups").status_code, 403)
                self.assertEqual(client.get("/api/v1/backups").status_code, 403)
                client.post("/api/v1/admin/unlock", headers={"x-arena-local": "1"})
                session = client.post("/api/v1/sessions", json={"name": "Private"}).json()
                client.post(f"/api/v1/sessions/{session['id']}/submit", json={"source": "frozen private CPP"})
                job = client.post("/api/v1/backups", headers={"idempotency-key": "snapshot"}).json()
                deadline = time.monotonic()+15
                while time.monotonic() < deadline:
                    finished = client.get(f"/api/v1/jobs/{job['id']}").json()
                    if finished["status"] in ("failed", "succeeded"):
                        break
                    time.sleep(.03)
                self.assertEqual(finished["status"], "succeeded", finished)
                identity = finished["result"]["backup_id"]
                row = client.get("/api/v1/backups").json()["items"][0]
                response = client.get(f"/api/v1/backups/{identity}")
                self.assertEqual(hashlib.sha256(response.content).hexdigest(), row["sha256"])
                self.assertNotIn("path", row)
                client.cookies.clear()
                self.assertEqual(client.get(f"/api/v1/backups/{identity}").status_code, 403)
                with self.assertRaises(RuntimeError):
                    Queue(Store(root / "data")).lock_workspace()

    def test_frozen_source_changed_after_initial_validation_is_not_archived_as_complete(self):
        from service.backup import verify_restored_records
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, _, _, submitted, _ = self.prepared(root, queued=False)
            def change_after_validation(records):
                verify_restored_records(records)
                Path(submitted["source"]).write_text("changed between verification and capture", encoding="utf-8")
            with patch("service.backup.verify_restored_records", side_effect=change_after_validation):
                with self.assertRaisesRegex(ValueError, "Archived bytes differ"):
                    create_backup(store)
            self.assertEqual(store.list("backup"), [])
            self.assertEqual(list((store.root / "backups").glob("*.zip")), [])


if __name__ == "__main__":
    unittest.main()
