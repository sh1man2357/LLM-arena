import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools.check_repository import credentials, private_path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseChecks(unittest.TestCase):
    def test_public_source_and_private_data_are_distinguished(self):
        for name in ('artifacts/local/arena.sqlite3', '.env', '.env.production', 'web/dist/index.html',
                     '.tools/compiler.exe', 'configs/private/token.json', 'backup.zip', 'bot.wasm'):
            self.assertTrue(private_path(name), name)
        for name in ('README.md', 'configs/public-dev.json', 'LICENSE', '.env.example', 'docs/images/home.png'):
            self.assertFalse(private_path(name), name)

    def test_common_credentials_are_detected_without_printing_values(self):
        self.assertEqual(credentials(('ghp_' + 'a'*36).encode()), ['GitHub token'])
        self.assertEqual(credentials(('-----BEGIN ' + 'PRIVATE KEY-----').encode()), ['private key'])
        self.assertEqual(credentials(b'API_KEY comes from the environment'), [])

    @unittest.skipUnless(os.name == 'nt', 'Windows setup scripts')
    def test_python_resolution_uses_explicit_and_standard_interpreters(self):
        script = str(ROOT / 'tools/python-runtime.ps1').replace("'", "''")
        interpreter = sys.executable.replace("'", "''")
        for command in (f"Resolve-ArenaPython -Python '{interpreter}'", 'Resolve-ArenaPython'):
            env = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH'])
            result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', f". '{script}'; {command}"],
                                    env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()).resolve(), Path(sys.executable).resolve())

    @unittest.skipUnless(os.name == 'nt', 'Windows browser launcher')
    def test_browser_launcher_refuses_the_product_port(self):
        result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                 str(ROOT / 'tools/test-browser.ps1'), '-Port', '8787'], capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('dedicated test port', result.stderr)
