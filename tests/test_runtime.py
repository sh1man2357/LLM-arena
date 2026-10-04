import struct
import tempfile
from pathlib import Path
import unittest
import wasmtime
from runtime.wasm import Backend, QualificationError, InitializationError, InfrastructureError
from runtime.protocol import encode
from engine.model import Bomb
from tests.test_engine import arena


def module(body="i32.const 0", init="", ptr=0, memory="(memory (export \"memory\") 2 1024)", extra=""):
    return wasmtime.wat2wasm(f'''(module {memory} {extra}
      (func (export "arena_init") (param i32 i32) {init})
      (func (export "arena_input_ptr") (result i32) i32.const {ptr})
      (func (export "arena_tick") (param i32 i32) (result i32) {body}))''')


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = Backend()
        cls.temp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.backend.close()
        cls.temp.cleanup()

    def load(self, data):
        path = Path(self.temp.name) / "bot.wasm"
        path.write_bytes(data)
        return self.backend.load(path)

    def test_protocol_layout(self):
        w = arena([(1, 1), (7, 5)])
        w.bombs = [Bomb(0, 1, 3, 3, 4, 3)]
        data = encode(w, 1)
        self.assertEqual(len(data), 48 + 63 + 32 + 24)
        self.assertEqual(struct.unpack("<12I", data[:48]), (1, 0, 9, 7, 1, 2, 1, 63, 500, 4, 1, 3))
        self.assertEqual(data[48:111], bytes(w.grid))
        self.assertEqual(struct.unpack("<4I", data[127:143]), (1, 7, 5, 1))
        self.assertEqual(struct.unpack("<6I", data[143:]), (0, 1, 3, 3, 4, 3))

    def test_fuel_trap_retains_memory_and_instance_recovers(self):
        # First call writes memory before looping; second reads it and returns RIGHT.
        data = module('''i32.const 65536 i32.load i32.eqz if
            i32.const 65536 i32.const 1 i32.store (loop $forever br $forever)
            end i32.const 2''')
        instance = self.backend.instance(self.load(data), 0, tick_fuel=100)
        try:
            self.assertEqual(instance.call(b"x")["fault"], "fuel")
            self.assertEqual(instance.call(b"x")["raw_action"], 2)
        finally:
            instance.close()

    def test_seed_high_low_and_independent_memory(self):
        data = module("i32.const 65536 i32.load", "i32.const 65536 local.get 1 i32.store")
        first = self.backend.instance(self.load(data), 2 << 32)
        second = self.backend.instance(self.load(data), 3 << 32)
        try:
            self.assertEqual(first.call(b"x")["raw_action"], 2)
            self.assertEqual(second.call(b"x")["raw_action"], 3)
        finally:
            first.close(); second.close()

    def test_invalid_and_crash(self):
        for body, expected in [("i32.const 99", "invalid_action"),
                               ("unreachable", "trap"), ("i32.const 2147483647 i32.load", "trap")]:
            instance = self.backend.instance(self.load(module(body)), 1)
            try:
                self.assertEqual(instance.call(b"x")["fault"], expected)
            finally:
                instance.close()

    def test_memory_growth_limit(self):
        data = module("i32.const 1023 memory.grow")
        instance = self.backend.instance(self.load(data), 1)
        try:
            self.assertEqual(instance.call(b"x")["raw_action"], -1)
            self.assertEqual(instance.memory.size(instance.store), 2)
        finally:
            instance.close()

    def test_initialization_failures(self):
        for data in (module(init="unreachable"), module(ptr=131072),
                     module(init="(loop $l br $l)")):
            with self.assertRaises(InitializationError):
                self.backend.instance(self.load(data), 1, init_fuel=100)

    def test_watchdog_is_infrastructure_failure(self):
        instance = self.backend.instance(self.load(module()), 1)
        original = instance.store.set_epoch_deadline
        instance.store.set_epoch_deadline = lambda _: original(0)
        try:
            with self.assertRaises(InfrastructureError):
                instance.call(b"x")
        finally:
            instance.close()

    def test_forbidden_modules(self):
        invalid = [module(memory='(memory (export "memory") 2)'),
                   module(memory='(memory (export "memory") 2 1025)'),
                   module(extra='(func $start) (start $start)'),
                   wasmtime.wat2wasm('(module (import "host" "f" (func)))'),
                   wasmtime.wat2wasm('(module (memory (export "memory") 2 1024))'),
                   module(extra='(memory 1 2)'),
                   module(memory='(memory (export "memory") 2 1024 shared)'),
                   module(memory='(memory (export "memory") i64 2 1024)'),
                   b"invalid"]
        for data in invalid:
            with self.assertRaises(QualificationError):
                self.load(data)


if __name__ == "__main__":
    unittest.main()
