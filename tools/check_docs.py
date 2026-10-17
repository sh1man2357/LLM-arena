"""Validate current documents without Git history or historical archives."""
from pathlib import Path
import argparse
import re
from urllib.parse import unquote, urlsplit
ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--links-only', action='store_true', help='Compatibility alias for current document checks')
    parser.parse_args()
    files = [ROOT / name for name in ('README.md', 'AGENTS.md', 'CHANGELOG.md', 'CONTRIBUTING.md', 'SECURITY.md', 'THIRD_PARTY_NOTICES.md') if (ROOT / name).exists()]
    files += [*sorted((ROOT / 'docs').rglob('*.md')), *sorted((ROOT / 'devkit').glob('*.md'))]
    links = 0
    for path in files:
        text = path.read_text(encoding='utf-8')
        if len(re.findall(r'^```', text, re.M)) % 2:
            raise ValueError(f'Unbalanced code fences: {path}')
        prose = re.sub(r'^```[^\n]*\n.*?^```[^\n]*$', '', text, flags=re.M | re.S)
        for link in re.findall(r'\]\(([^)]+)\)', prose):
            target = urlsplit(link.strip().strip('<>'))
            if target.scheme or target.netloc or not target.path:
                continue
            if not (path.parent / unquote(target.path)).exists():
                raise ValueError(f'Missing local link: {path} -> {link}')
            links += 1
    print(f'Verified {len(files)} documents, {links} local links and code fences.')

if __name__ == '__main__': main()
