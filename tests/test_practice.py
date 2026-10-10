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

    def test_multiplayer_rotates_all_slots_and_keeps_seeds_with_instances(self):
        case = read_json(ROOT / 'configs/public-dev.json')[0]
        for players in (3, 8):
            output = self.root / f'practice-{players}'
            with patch('tools.practice.ROOT', self.root):
                result = practice(None, self.candidate, output, ('random',), 1, players)
            self.assertEqual(result['player_count'], players)
            self.assertEqual(result['game_mode'], 'free_for_all')
            self.assertEqual(result['matches'], players)
            self.assertEqual(result['mean_placement'], .5)
            self.assertEqual(result['opponents'][0]['draws'], players)
            for slot in range(players):
                records = read(output / 'replays' / f'random-00-slot-{slot}.jsonl')
                header = records[0]
                self.assertEqual(len(header['entrants']), players)
                self.assertEqual(header['entrants'][slot]['id'], 'candidate')
                self.assertEqual(header['bot_seeds'][slot], case['bot_seeds'][0])
                seeds = case['bot_seeds'][:players]
                self.assertEqual(header['bot_seeds'], seeds[-slot:] + seeds[:-slot] if slot else seeds)
                verify_world(records)

    def test_multiplayer_tied_first_uses_placement_points(self):
        cases = read_json(self.root / 'configs/public-dev.json')
        cases[0]['bot_seeds'] = [f'{seed:016x}' for seed in range(8)]
        write_json(self.root / 'configs/public-dev.json', cases)
        # Odd seeds trap after the smoke call; even seeds remain alive.
        baseline = self.root / 'bots/baselines/random.wasm'
        baseline.write_bytes(module('''local.get 0 i32.const 4 i32.add i32.load
            i32.const 0 i32.gt_u
            i32.const 65536 i32.load i32.const 1 i32.and i32.and
            if unreachable end i32.const 0''', 'i32.const 65536 local.get 0 i32.store'))
        manifest = read_json(self.root / 'devkit-manifest.json')
        manifest['files']['bots/baselines/random.wasm']['sha256'] = sha_file(baseline)
        write_json(self.root / 'devkit-manifest.json', manifest)
        with patch('tools.practice.ROOT', self.root):
            result = practice(None, self.candidate, self.root / 'practice', ('random',), 1, 3)
        self.assertEqual(result['matches'], 3)
        self.assertEqual(result['mean_placement'], .75)
        self.assertEqual(result['opponents'][0]['draws'], 3)

    def test_invalid_player_count_or_missing_seeds_has_no_output(self):
        for players in (1, 9, 3.0, True):
            output = self.root / f'invalid-{players}'
            with patch('tools.practice.ROOT', self.root), self.assertRaisesRegex(ValueError, '2..8'):
                practice(None, self.candidate, output, ('random',), 1, players)
            self.assertFalse(output.exists())
        cases = read_json(self.root / 'configs/public-dev.json')
        cases[0]['bot_seeds'] = cases[0]['bot_seeds'][:2]
        write_json(self.root / 'configs/public-dev.json', cases)
        with patch('tools.practice.ROOT', self.root), self.assertRaisesRegex(ValueError, 'one seed per player'):
            practice(None, self.candidate, self.root / 'missing-seeds', ('random',), 1, 3)

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
