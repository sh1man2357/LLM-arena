"""Validate local document links and code fences without shell quoting ambiguity."""
from pathlib import Path
import argparse
import hashlib
import io
import re
import subprocess
import sys
import tarfile
from urllib.parse import unquote, urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.io import ROOT, read_json, sha_file
from runner.match import components


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--links-only", action="store_true", help="Check documents without auditing frozen releases")
    args = parser.parse_args()
    evidence = ROOT / "artifacts/acceptance/v0.1-release"
    files = [ROOT/"README.md", ROOT/"MODEL_TASK.md", *sorted((ROOT/"docs").rglob("*.md")),
             *sorted((ROOT/"artifacts/acceptance").rglob("*.md"))]
    links = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        if len(re.findall(r"^```", text, re.M)) % 2:
            raise ValueError(f"Unbalanced code fences: {path}")
        prose = re.sub(r"^```[^\n]*\n.*?^```[^\n]*$", "", text, flags=re.M | re.S)
        for link in re.findall(r"\]\(([^\)]+)\)", prose):
            target = urlsplit(link.strip().strip("<>"))
            if target.scheme or target.netloc or not target.path:
                continue
            if not (path.parent/unquote(target.path)).exists():
                raise ValueError(f"Missing local link: {path} -> {link}")
            links += 1
    migration = read_json(ROOT/"docs/path-map.json")
    for move in migration["moves"]:
        if not (ROOT/move["new"]).is_file():
            raise ValueError(f"Missing moved document: {move['new']}")
    if args.links_only:
        print(f"Verified {len(files)} documents, {links} local links, code fences and {len(migration['moves'])} path mappings.")
        return
    delivery = (ROOT/"docs/releases/v0.1.md").read_text(encoding="utf-8")
    if "- [ ]" in delivery or delivery.count("- [x]") != 29:
        raise ValueError("Delivery checklist is incomplete")
    next_delivery = (ROOT/"docs/releases/v0.2.md").read_text(encoding="utf-8")
    if next_delivery.count("- [ ]") + next_delivery.count("- [x]") != 29:
        raise ValueError("v0.2 delivery checklist count differs")
    frozen = read_json(evidence/"manifest.json")["components"]
    # v0.2 legitimately extends runner code. Audit the immutable v0.1 Git tree,
    # rather than demanding that current development impersonate that version.
    archive = subprocess.run(["git", "archive", "--format=tar", "69bdca4"], cwd=ROOT,
                             check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
        for name, expected in frozen["source_files"].items():
            source = tree.extractfile(name)
            if source is None or hashlib.sha256(source.read()).hexdigest() != expected:
                raise ValueError(f"Frozen v0.1 tree differs: {name}")
    # The migration map points to exact historical bytes, not the edited documents.
    snapshot = subprocess.run(["git", "archive", "--format=tar", migration["snapshot_commit"]], cwd=ROOT,
                              check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(snapshot)) as tree:
        for move in migration["moves"]:
            source = tree.extractfile(move["old"])
            if source is None or hashlib.sha256(source.read()).hexdigest() != move["original_sha256"]:
                raise ValueError(f"Historical document differs: {move['old']}")
    checksum = sha_file(evidence/"evidence.zip")
    if (read_json(evidence/"evidence.index.json")["sha256"] != checksum or
            read_json(evidence/"checks/archive-restore.json")["archive_sha256"] != checksum):
        raise ValueError("Evidence archive/checksum differs")
    print(f"Verified {len(files)} documents, {links} local links, v0.1 acceptance and v0.2 checklist structure, historical document hashes, frozen v0.1 tree and archive hashes. Current benchmark: {components()['benchmark_id']}.")


if __name__ == "__main__": main()
