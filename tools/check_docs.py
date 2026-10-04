"""Validate local document links and code fences without shell quoting ambiguity."""
from pathlib import Path
import re
import sys
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
    if read_json(evidence/"manifest.json")["components"] != components():
        raise ValueError("Source differs from frozen manifest")
    checksum = sha_file(evidence/"evidence.zip")
    if (read_json(evidence/"evidence.index.json")["sha256"] != checksum or
            read_json(evidence/"checks/archive-restore.json")["archive_sha256"] != checksum):
        raise ValueError("Evidence archive/checksum differs")
    print(f"Verified {len(files)} documents, v0.1 acceptance and v0.2 checklist structure, frozen components and archive hashes.")


if __name__ == "__main__": main()
