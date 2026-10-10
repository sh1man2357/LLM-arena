"""Generated reference evidence, all-or-nothing imports and immutable public copies."""
from service.reference import reference_archive
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
from engine.model import digest
from runner.io import ROOT, sha_file, write_json, write_lines, read_json
from runner.tournament import schedule
from service.app import create_app
from service.imports import extract_archive, import_tournament, import_uploaded_archive, alias_id
from service.publication import close_submissions, publish_tournament
from service.store import Store
from service.replays import from_bytes


def fixture(folder, *, wasm=True):
    """Two actual generated matches, preserving original headers and WASM."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(reference_archive()) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        manifest["entrants"] = manifest["entrants"][:2]
        cases = json.loads(archive.read("cases.json"))[:1]
        plan = schedule(manifest["entrants"], cases)
        manifest.update(cases_sha256=digest(cases), schedule_sha256=digest(plan), expected_matches=2)
        results = {r["match_id"]: r for r in map(json.loads, archive.read("results.jsonl").splitlines())}
        write_json(folder / "manifest.json", manifest)
        write_json(folder / "cases.json", cases)
        write_json(folder / "schedule.json", plan)
        write_lines(folder / "results.jsonl", [results[p["match_id"]] for p in plan])
        (folder / "replays").mkdir()
        for item in plan:
            name = f"replays/{item['match_id']}.jsonl"
            (folder / name).write_bytes(archive.read(name))
        if wasm:
            (folder / "build").mkdir()
            for entrant in manifest["entrants"]:
                name = f"build/{entrant['id']}.wasm"
                (folder / name).write_bytes(archive.read(name))
    (folder / "report.md").write_text("original archived report, unchanged\n", encoding="utf-8")
    return manifest, plan


def archive_bytes(folder):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in Path(folder).rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(folder).as_posix())
    return target.getvalue()


class EvidenceLifecycleTests(unittest.TestCase):
    def test_public_projection_drops_private_header_extensions(self):
        with zipfile.ZipFile(reference_archive()) as archive:
            records = [json.loads(line) for line in archive.read("examples/chain/replay.jsonl").splitlines()]
        private = "PRIVATE_ONLY_SENTINEL"
        records[0]["budget"]["private_seed"] = private
        records[0]["initialization"][0]["source_path"] = private
        records[0]["initial_state"]["private_seed"] = private
        data = "\n".join(json.dumps(r) for r in records).encode()
        ui = from_bytes(data)
        self.assertTrue(ui["verified"])
        self.assertNotIn(private, json.dumps(ui))
        records[0]["initial_state"]["players"][0]["source_path"] = private
        with self.assertRaises(ValueError):
            from_bytes("\n".join(json.dumps(r) for r in records).encode())
        del records[0]["initial_state"]["players"][0]["source_path"]
        records[0]["initialization"][0]["fuel_used"] = "C:/private/path"
        with self.assertRaises(ValueError):
            from_bytes("\n".join(json.dumps(r) for r in records).encode())
        records[0]["initialization"][0]["fuel_used"] = 14
        records[0]["components"]["source_hash"] = "C:/private/path"
        with self.assertRaises(ValueError):
            from_bytes("\n".join(json.dumps(r) for r in records).encode())
        records[0]["components"]["source_hash"] = "a"*64
        records[-1].update(valid=False, reason="infrastructure_failure", players=[{"source_path": private}])
        for stats in records[-1]["stats"]:
            stats["private_seed"] = private
        failed = from_bytes("\n".join(json.dumps(r) for r in records).encode())
        self.assertFalse(failed["verified"])
        self.assertEqual(failed["result"]["players"], [])
        self.assertNotIn(private, json.dumps(failed))
        records[0]["entrants"][0]["wasm_sha256"] = "C:/private/path"
        with self.assertRaises(ValueError):
            from_bytes("\n".join(json.dumps(r) for r in records).encode())

    def test_import_preserves_raw_files_namespaces_ids_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, plan = fixture(root / "legacy")
            hashes = {p.relative_to(root / "legacy").as_posix(): sha_file(p) for p in (root / "legacy").rglob("*") if p.is_file()}
            store = Store(root / "data")
            # A pre-existing same name must not be rebound to archived code.
            eid = manifest["entrants"][0]["id"]
            store.put("entrant", dict(id=eid, name="Existing", wasm_sha256="f"*64, status="historical"))
            first = import_tournament(store, root / "legacy", "legacy-test", source_hash="a"*64)
            second = import_tournament(store, root / "legacy", "legacy-test", source_hash="a"*64)
            self.assertEqual(first, second)
            self.assertEqual(len(store.list("match")), 2)
            self.assertEqual(store.get("entrant", eid)["wasm_sha256"], "f"*64)
            imported = store.get("entrant", alias_id(eid, manifest["entrants"][0]["wasm_sha256"]))
            self.assertEqual(imported["status"], "qualified")
            self.assertFalse(imported["baseline"])
            self.assertEqual(imported["name"], eid)
            self.assertEqual(hashes, {p.relative_to(root / "legacy").as_posix(): sha_file(p) for p in (root / "legacy").rglob("*") if p.is_file()})
            ids = {e["id"] for e in first["report"]["entrants"]}
            for row in store.list("match"):
                self.assertEqual({e["id"] for e in row["entrants"]}, ids)
                self.assertEqual(set(row["case"]["pair"]), ids)
                self.assertEqual({e["id"] for e in read_json(row["projection"])["entrants"]}, ids)
            self.assertEqual(first["report"]["valid_matches"], 2)
            with self.assertRaises(FileExistsError):
                import_tournament(store, root / "legacy", "legacy-test", source_hash="b"*64)

    def test_late_validation_and_transaction_failure_leave_no_visible_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, plan = fixture(root / "legacy")
            store = Store(root / "data")
            bad = root / "legacy/build" / f"{manifest['entrants'][-1]['id']}.wasm"
            original = bad.read_bytes()
            bad.write_bytes(original + b"modified")
            with self.assertRaises(ValueError):
                import_tournament(store, root / "legacy", "legacy-test")
            self.assertEqual(store.list("match"), [])
            self.assertEqual(store.list("tournament"), [])
            self.assertEqual(store.list("entrant"), [])
            bad.write_bytes(original)
            original_put = store.put
            def failing_put(kind, value, **kwargs):
                if kind == "tournament":
                    raise OSError("simulated index commit failure")
                return original_put(kind, value, **kwargs)
            with patch.object(store, "put", side_effect=failing_put), self.assertRaises(OSError):
                import_tournament(store, root / "legacy", "legacy-test")
            self.assertEqual(store.list("match"), [])
            self.assertEqual(store.list("entrant"), [])
            self.assertEqual(import_tournament(store, root / "legacy", "legacy-test")["status"], "complete")

    def test_archive_windows_collisions_symlinks_and_limits_fail_before_extraction(self):
        variants = [[("safe.txt", "ok"), ("../escape", "bad")], [("A.txt", "a"), ("a.txt", "b")],
                    [("a", "file"), ("a/b", "nested")], [("name.", "alias")], [("CON.txt", "device")],
                    [("large", "x"*(16*1024*1024+1))]]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, entries in enumerate(variants):
                path = root / f"bad-{index}.zip"
                with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                    for name, data in entries:
                        archive.writestr(name, data)
                destination = root / f"extract-{index}"
                with self.assertRaises(ValueError):
                    extract_archive(path, destination)
                self.assertFalse(destination.exists())
            path = root / "symlink.zip"
            link = zipfile.ZipInfo("link")
            link.external_attr = 0o120777 << 16
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(link, "../../outside")
            with self.assertRaises(ValueError):
                extract_archive(path, root / "link-extract")

    def test_publication_is_fixed_hash_linked_private_safe_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root / "legacy", wasm=False)
            app = create_app(root / "data")
            store = app.state.store
            row = import_tournament(store, root / "legacy", "legacy-test")
            store.update("tournament", row["id"], lambda r: r.update(official=True, submission_window_closed=False))
            with TestClient(app) as client:
                client.post("/api/v1/admin/unlock", headers={"x-arena-local": "1"})
                self.assertEqual(client.post("/api/v1/tournaments/legacy-test/publish").status_code, 409)
                closed = client.post("/api/v1/tournaments/legacy-test/close-submissions").json()
                self.assertEqual(client.post("/api/v1/tournaments/legacy-test/close-submissions").json()["window_closed_at"], closed["window_closed_at"])
                published = client.post("/api/v1/tournaments/legacy-test/publish").json()
                self.assertEqual(published["disclosure"], "archived")
                repeated = client.post("/api/v1/tournaments/legacy-test/publish").json()
                self.assertEqual(published, repeated)
                self.assertEqual(client.post("/api/v1/tournaments/legacy-test/close-submissions").json(), repeated)
                client.cookies.clear()
                exported = client.get("/api/v1/exports/legacy-test?kind=publication")
                self.assertEqual(exported.status_code, 200)
                manifest = exported.json()
                self.assertEqual(hashlib.sha256(exported.content).hexdigest(), published["publication_sha256"])
                report = client.get("/api/v1/exports/legacy-test?kind=report")
                self.assertEqual(hashlib.sha256(report.content).hexdigest(), manifest["report"]["public_sha256"])
                for match in manifest["matches"]:
                    response = client.get(f"/api/v1/exports/{match['id']}")
                    self.assertEqual(hashlib.sha256(response.content).hexdigest(), match["public_sha256"])
                    self.assertEqual(response.json()["source_sha256"], match["source_sha256"])
                    # Mutating the UI cache cannot change a published copy.
                    row = store.get("match", match["id"])
                    Path(row["projection"]).write_text('{"private_seed":"injected"}')
                    self.assertEqual(response.content, client.get(f"/api/v1/exports/{match['id']}").content)
                    for forbidden in ("map_seed", "bot_seeds", "source_files", "diagnostic", str(root)):
                        self.assertNotIn(forbidden, response.text)
                record = store.get("publication", published["publication_id"])
                (Path(record["directory"]) / "report.json").write_text("modified")
                self.assertEqual(client.get("/api/v1/exports/legacy-test?kind=report").status_code, 409)
                self.assertEqual(client.get("/api/v1/exports/legacy-test?kind=unknown").status_code, 422)
                (Path(record["directory"]) / "report.json").unlink()
                self.assertEqual(client.get("/api/v1/exports/legacy-test?kind=report").status_code, 409)

    def test_real_worker_archive_upload_idempotence_logs_and_corrupt_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root / "legacy", wasm=False)
            data = archive_bytes(root / "legacy")
            app = create_app(root / "data", workers=True)
            with TestClient(app) as client:
                self.assertEqual(client.post("/api/v1/imports/archive", files={"file": ("old.zip", data)}).status_code, 403)
                client.post("/api/v1/admin/unlock", headers={"x-arena-local": "1"})
                headers = {"idempotency-key": "same-archive"}
                first = client.post("/api/v1/imports/archive?title=Historical", headers=headers, files={"file": ("old.zip", data)})
                self.assertEqual(first.status_code, 202)
                job = first.json()
                again = client.post("/api/v1/imports/archive?title=Historical", headers=headers, files={"file": ("old.zip", data)})
                self.assertEqual(again.json()["id"], job["id"])
                self.assertEqual(client.post("/api/v1/imports/archive?title=Changed", headers=headers, files={"file": ("old.zip", data)}).status_code, 409)
                def wait(identity):
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        row = client.get(f"/api/v1/jobs/{identity}").json()
                        if row["status"] in ("succeeded", "failed"):
                            return row
                        time.sleep(.03)
                    self.fail("Import worker did not finish")
                result = wait(job["id"])
                self.assertEqual(result["status"], "succeeded", result)
                batch = client.get(f"/api/v1/tournaments/{result['result']['tournament_id']}").json()
                self.assertEqual(batch["title"], "Historical")
                self.assertEqual(batch["report"]["valid_matches"], 2)
                identity = batch["id"]
                self.assertTrue(batch["requires_disclosure_confirmation"])
                self.assertEqual(client.post(f"/api/v1/tournaments/{identity}/publish").status_code, 409)
                owner_cookies = dict(client.cookies)
                client.cookies.clear()
                self.assertEqual(client.get(f"/api/v1/tournaments/{identity}").status_code, 403)
                self.assertEqual(client.get("/api/v1/matches", params={"tournament_id": identity}).json()["total"], 0)
                client.cookies.update(owner_cookies)
                closed = client.post(f"/api/v1/tournaments/{identity}/close-submissions").json()
                self.assertEqual({e["id"] for e in closed["window_closed_entrants"]}, {e["id"] for e in batch["report"]["entrants"]})
                self.assertEqual(closed["window_close_source"], "host_confirmation")
                client.cookies.clear()
                self.assertEqual(client.get(f"/api/v1/tournaments/{identity}").status_code, 200)
                client.cookies.update(owner_cookies)
                invalid = client.post("/api/v1/imports/archive", files={"file": ("bad.zip", b"not a zip")}).json()
                failed = wait(invalid["id"])
                self.assertEqual(failed["status"], "failed")
                self.assertIn("Archive cannot be read", client.get(f"/api/v1/jobs/{invalid['id']}/log").text)
                self.assertEqual(len(app.state.store.list("tournament")), 1)
                self.assertEqual(len(app.state.store.list("match")), 2)


if __name__ == "__main__":
    unittest.main()
