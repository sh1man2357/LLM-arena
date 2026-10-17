"""Check publishable Git paths, reachable blob sizes and common credential formats."""
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'private key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'GitHub token': re.compile(rb'(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,})'),
    'API key': re.compile(rb'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}'),
    'AWS access key': re.compile(rb'AKIA[0-9A-Z]{16}'),
}


def private_path(name):
    path = PurePosixPath(name)
    prefixes = ('artifacts/', '.venv/', '.tools/', 'configs/private/', 'web/node_modules/',
                'web/dist/', 'web/test-results/', 'web/playwright-report/')
    return (name.startswith(prefixes) or path.name == '.env' or
            (path.name.startswith('.env.') and path.name != '.env.example') or
            path.suffix.lower() in ('.wasm', '.zip', '.sqlite', '.sqlite3', '.db', '.pem', '.key'))


def credentials(data):
    return [name for name, pattern in PATTERNS.items() if pattern.search(data)]


def git(*args, input=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, input=input)


def main():
    tracked = git('ls-files', '-z').decode('utf-8').split('\0')
    errors = [f'Generated/private tracked path: {p}' for p in tracked if p and private_path(p)]
    objects = git('rev-list', '--objects', '--all')
    metadata = git('cat-file', '--batch-check=%(objectname) %(objecttype) %(objectsize) %(rest)', input=objects)
    blobs = []
    for line in metadata.decode('utf-8').splitlines():
        oid, kind, size, *path = line.split(' ', 3)
        if kind != 'blob':
            continue
        name = path[0] if path else oid
        if private_path(name):
            errors.append(f'Generated/private path in reachable history: {name}')
        if int(size) > 100 * 1024 * 1024:
            errors.append(f'Blob exceeds 100 MiB: {name}')
        blobs.append((oid, name))
    with subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
        for oid, name in blobs:
            process.stdin.write((oid + '\n').encode())
            process.stdin.flush()
            header = process.stdout.readline().split()
            remaining, tail, found = int(header[2]), b'', set()
            while remaining:
                chunk = process.stdout.read(min(65536, remaining))
                if not chunk:
                    raise ValueError('Truncated Git blob stream')
                remaining -= len(chunk)
                found.update(credentials(tail + chunk))
                tail = chunk[-512:]
            process.stdout.read(1)
            for label in sorted(found):
                errors.append(f'{label} pattern: {name} ({oid[:12]}); value omitted')
        process.stdin.close()
        if process.wait() != 0:
            raise ValueError('Git blob scan failed')
    if errors:
        raise ValueError('\n'.join(sorted(set(errors))))
    print(f'Checked {sum(bool(p) for p in tracked)} tracked files and {len(blobs)} reachable historical blobs; no blocked paths, oversized blobs or common credential patterns.')
    print('Pattern checks do not replace review of private data and third-party rights.')


if __name__ == '__main__':
    main()
