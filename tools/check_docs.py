"""Validate local document links and code fences without shell quoting ambiguity."""
from pathlib import Path
import hashlib
import io
import re
import subprocess
import sys
import tarfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.io import ROOT, read_json, sha_file
from runner.match import components


def main():
    evidence = ROOT / "artifacts/acceptance/v0.1-release"
    files = [ROOT/"README.md", ROOT/"DELIVERY.md", ROOT/"DELIVERY_v0.2.md", ROOT/"MODEL_TASK.md", *(ROOT/"docs").glob("*.md"),
             evidence/"handoff.md", evidence/"audit.md"]
    for path in files:
        text = path.read_text(encoding="utf-8")
        if len(re.findall(r"^```", text, re.M)) % 2:
            raise ValueError(f"Unbalanced code fences: {path}")
        for link in re.findall(r"\]\((\.\.?/[^\)]+)\)", text):
            if not (path.parent/link).exists():
                raise ValueError(f"Missing local link: {path} -> {link}")
    delivery = (ROOT/"DELIVERY.md").read_text(encoding="utf-8")
    if "- [ ]" in delivery or delivery.count("- [x]") != 29:
        raise ValueError("Delivery checklist is incomplete")
    next_delivery = (ROOT/"DELIVERY_v0.2.md").read_text(encoding="utf-8")
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
    checksum = sha_file(evidence/"evidence.zip")
    if (read_json(evidence/"evidence.index.json")["sha256"] != checksum or
            read_json(evidence/"checks/archive-restore.json")["archive_sha256"] != checksum):
        raise ValueError("Evidence archive/checksum differs")
    print(f"Verified {len(files)} documents, v0.1 acceptance and v0.2 checklist structure, frozen v0.1 tree and archive hashes. Current benchmark: {components()['benchmark_id']}.")


if __name__ == "__main__": main()
