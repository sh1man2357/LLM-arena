from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from runner.io import ROOT, read_json, sha_file, write_json
from tests.test_runtime import module
from tools.practice import practice
from replay.verify import read, verify_world


class PracticeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='llm-arena-practice-test-')
        self.root = Path(self.temp.name).resolve()
        assert self.root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        write_json(self.root / 'configs/public-dev.json', read_json(ROOT / 'configs/public-dev.json'))
        files = {}
        for name in ('random', 'safe', 'heuristic'):
            target = self.root / f'bots/baselines/{name}.wasm'
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(module())
            files[target.relative_to(self.root).as_posix()] = {'sha256': sha_file(target)}
        write_json(self.root / 'devkit-manifest.json', {'files': files})
        self.candidate = self.root / 'candidate.wasm'
        self.candidate.write_bytes(module())

    def tearDown(self):
        self.temp.cleanup()

    def test_public_pairing_swaps_and_runtime_budgets(self):
        output = self.root / 'practice'
        with patch('tools.practice.ROOT', self.root):
            result = practice(None, self.candidate, output, ('random', 'safe', 'heuristic'), 1)
        self.assertEqual(result['matches'], 6)
        self.assertEqual(result['mean_placement'], .5)
        case = read_json(ROOT / 'configs/public-dev.json')[0]
        for name in ('random', 'safe', 'heuristic'):
            first = read(output / 'replays' / f'{name}-00-first.jsonl')
            swapped = read(output / 'replays' / f'{name}-00-swap.jsonl')
            self.assertEqual(first[0]['map_seed'], case['map_seed'])
            self.assertEqual([e['id'] for e in swapped[0]['entrants']], [e['id'] for e in first[0]['entrants']][::-1])
            self.assertEqual(swapped[0]['bot_seeds'], first[0]['bot_seeds'][::-1])
            self.assertEqual(first[0]['budget'], {'init_fuel': 10_000_000, 'tick_fuel': 1_000_000})
            verify_world(first); verify_world(swapped)

    def test_changed_frozen_baseline_cannot_run(self):
        baseline = self.root / 'bots/baselines/random.wasm'
        baseline.write_bytes(baseline.read_bytes() + b'changed')
        with patch('tools.practice.ROOT', self.root), self.assertRaisesRegex(ValueError, 'frozen devkit'):
            practice(None, self.candidate, self.root / 'practice', ('random',), 1)

    def test_existing_output_is_never_overwritten(self):
        output = self.root / 'practice'
        output.mkdir()
        marker = output / 'keep.txt'
        marker.write_text('prior run', encoding='utf-8')
        with patch('tools.practice.ROOT', self.root), self.assertRaisesRegex(ValueError, 'already exists'):
            practice(None, self.candidate, output, ('random',), 1)
        self.assertEqual(marker.read_text(encoding='utf-8'), 'prior run')

    def test_unqualified_candidate_has_no_score(self):
        self.candidate.write_bytes(module('i32.const 99'))
        output = self.root / 'practice'
        with patch('tools.practice.ROOT', self.root), self.assertRaisesRegex(ValueError, 'smoke check failed'):
            practice(None, self.candidate, output, ('random',), 1)
        self.assertFalse((output / 'summary.json').exists())


if __name__ == '__main__':
    unittest.main()
