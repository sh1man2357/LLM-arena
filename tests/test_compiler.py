from pathlib import Path
import tempfile
import unittest
from engine.maps import generate
from engine.model import Bomb, Player, World
from runtime.protocol import encode
from runtime.wasm import Backend, QualificationError, InitializationError
from runner.compiler import compile_bot
from runner.io import ROOT, read_json


class CompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        cls.backend = Backend()

    @classmethod
    def tearDownClass(cls):
        cls.backend.close(); cls.temp.cleanup()

    def compile_text(self, name, text):
        source = self.folder / f"{name}.cpp"; source.write_text(text, encoding="utf-8")
        output = self.folder / f"{name}.wasm"
        compile_bot(source, output)
        return output

    def test_stl_constructor_seed_and_observation(self):
        output = self.folder / "probe.wasm"
        meta = compile_bot(ROOT / "tests/fixtures/sdk_probe.cpp", output)
        self.assertIn(str((ROOT / "sdk/arena.hpp").resolve()), meta["dependencies"])
        m = generate(1)
        w = World(13, 11, m["grid"], [Player(i, *p) for i, p in enumerate(m["spawns"])])
        w.bombs = [Bomb(0, 0, 1, 1, 4, 3)]
        instance = self.backend.instance(self.backend.load(output), 0xfedcba9876543210)
        try:
            self.assertEqual(instance.call(encode(w, 1))["raw_action"], 2)
            self.assertEqual(instance.call(encode(w, 1))["raw_action"], 3)
        finally: instance.close()

    def test_actual_cpp_fuel_trap_recovers(self):
        path = self.compile_text("fuel", '''#include "arena.hpp"
            static volatile unsigned n;
            namespace bot {void init(uint64_t){} Action tick(const GameState&){
                n=n+1; while(n==1){} return Action::RIGHT;}}''')
        m = generate(1); w = World(13, 11, m["grid"], [Player(i, *p) for i, p in enumerate(m["spawns"])])
        instance = self.backend.instance(self.backend.load(path), 1, tick_fuel=10000)
        try:
            self.assertEqual(instance.call(encode(w, 0))["fault"], "fuel")
            self.assertEqual(instance.call(encode(w, 0))["raw_action"], 2)
        finally: instance.close()

    def test_compile_failure_and_host_import(self):
        source = self.folder / "broken.cpp"; source.write_text("not valid C++", encoding="utf-8")
        with self.assertRaises(ValueError): compile_bot(source, self.folder / "broken.wasm")
        self.assertNotEqual(read_json(self.folder / "broken.compile.json")["exit_code"], 0)
        path = self.compile_text("stdio", '''#include "arena.hpp"
            #include <cstdio>
            namespace bot {void init(uint64_t){} Action tick(const GameState&){puts("forbidden");return Action::WAIT;}}''')
        with self.assertRaises(QualificationError): self.backend.load(path)

    def test_allocation_cap_traps_without_import(self):
        path = self.compile_text("memory", '''#include "arena.hpp"
            #include <new>
            static char* volatile allocated;
            namespace bot {void init(uint64_t){allocated=new char[67108864];}
            Action tick(const GameState&){return Action::WAIT;}}''')
        with self.assertRaises(InitializationError): self.backend.instance(self.backend.load(path), 1)


if __name__ == "__main__":
    unittest.main()
