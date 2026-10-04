"""No-import Wasmtime instances with deterministic fuel and an infrastructure watchdog."""
import hashlib
import importlib.metadata
from pathlib import Path
import threading
import wasmtime
from wasmtime import _bindings as ffi

VERSION = "49.0.0"
MEMORY_LIMIT = 64 * 1024 * 1024
TICK_FUEL = 1_000_000
INIT_FUEL = 10_000_000
DISABLED_FEATURES = ("wasm_threads", "wasm_memory64", "wasm_multi_memory", "wasm_simd",
                     "wasm_relaxed_simd", "wasm_reference_types", "wasm_function_references",
                     "wasm_gc", "wasm_exceptions", "wasm_tail_call", "wasm_stack_switching",
                     "wasm_component_model", "wasm_custom_page_sizes", "wasm_wide_arithmetic")


class QualificationError(ValueError):
    pass


class InitializationError(ValueError):
    pass


class InfrastructureError(RuntimeError):
    pass


def check_sections(data):
    if len(data) > 8 * 1024 * 1024 or data[:8] != b"\x00asm\x01\x00\x00\x00":
        raise QualificationError("Expected core WASM v1, at most 8 MiB")
    offset = 8
    while offset < len(data):
        sid = data[offset]
        offset += 1
        size = 0
        for shift in range(0, 35, 7):
            if offset >= len(data):
                raise QualificationError("Truncated WASM section")
            byte = data[offset]
            offset += 1
            size |= (byte & 127) << shift
            if byte < 128:
                break
        else:
            raise QualificationError("Invalid WASM section length")
        if sid == 8:
            raise QualificationError("WASM start section is forbidden")
        offset += size
        if offset > len(data):
            raise QualificationError("Truncated WASM section payload")


class Backend:
    def __init__(self):
        if importlib.metadata.version("wasmtime") != VERSION:
            raise InfrastructureError(f"Wasmtime must be {VERSION}")
        config = wasmtime.Config()
        config.consume_fuel = True
        config.epoch_interruption = True
        config.cranelift_nan_canonicalization = True
        config.max_wasm_stack = 1024 * 1024
        # 49.0.0's high-level wrapper omits these public C-API feature toggles.
        # Disable dependent component proposals before disabling reference types.
        for option in ("async", "more_async_builtins", "async_stackful"):
            getattr(ffi, f"wasmtime_config_wasm_component_model_{option}_set")(config.ptr(), False)
        config.wasm_component_model_map = False
        config.wasm_component_model_implements = False
        for feature in DISABLED_FEATURES:
            setattr(config, feature, False)
        config.wasm_bulk_memory = True
        config.wasm_multi_value = True
        self.engine = wasmtime.Engine(config)
        self.cache = {}
        self.stop = threading.Event()
        self.ticker = threading.Thread(target=self._clock, daemon=True)
        self.ticker.start()

    def _clock(self):
        while not self.stop.wait(.1):
            self.engine.increment_epoch()

    def load(self, path):
        data = Path(path).read_bytes()
        checksum = hashlib.sha256(data).hexdigest()
        if checksum in self.cache:
            return self.cache[checksum]
        check_sections(data)
        try:
            module = wasmtime.Module(self.engine, data)
        except wasmtime.WasmtimeError as exc:
            raise QualificationError(str(exc)) from exc
        if module.imports:
            raise QualificationError("All host/WASI imports are forbidden")
        exports = {e.name: e.type for e in module.exports}
        memory = exports.get("memory")
        if not isinstance(memory, wasmtime.MemoryType):
            raise QualificationError("Missing exported linear memory")
        if (memory.is_shared or memory.is_64 or memory.page_size != 65536 or
                memory.limits.max is None or memory.limits.max > 1024 or memory.limits.min > 1024):
            raise QualificationError("Memory must be wasm32, unshared, maximum <= 1024 pages")
        for name, params, results in (("arena_init", ["i32", "i32"], []),
                                       ("arena_input_ptr", [], ["i32"]),
                                       ("arena_tick", ["i32", "i32"], ["i32"])):
            ty = exports.get(name)
            if not isinstance(ty, wasmtime.FuncType) or list(map(str, ty.params)) != params or list(map(str, ty.results)) != results:
                raise QualificationError(f"Invalid export signature: {name}")
        self.cache[checksum] = module
        return module

    def instance(self, module, seed, init_fuel=INIT_FUEL, tick_fuel=TICK_FUEL):
        return BotInstance(self, module, seed, init_fuel, tick_fuel)

    def close(self):
        self.stop.set()
        self.ticker.join()
        for module in self.cache.values():
            module.close()
        self.engine.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class BotInstance:
    def __init__(self, backend, module, seed, init_fuel, tick_fuel):
        if type(seed) is not int or not 0 <= seed <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError("Bot seed must be uint64")
        self.store = wasmtime.Store(backend.engine)
        self.store.set_limits(memory_size=MEMORY_LIMIT, table_elements=65536, instances=1, memories=1, tables=1)
        self.tick_fuel = tick_fuel
        self.store.set_fuel(init_fuel)
        self.store.set_epoch_deadline(200)
        try:
            instance = wasmtime.Instance(self.store, module, [])
            self.exports = instance.exports(self.store)
            self.memory = self.exports["memory"]
            def signed(v):
                return v if v < 0x80000000 else v - 0x100000000
            self.exports["arena_init"](self.store, signed(seed & 0xFFFFFFFF), signed(seed >> 32))
            self.input_ptr = self.exports["arena_input_ptr"](self.store) & 0xFFFFFFFF
            if self.input_ptr + 65536 > self.memory.data_len(self.store):
                raise InitializationError("Input region does not fit allocated memory")
            self.init_fuel_used = init_fuel - self.store.get_fuel()
        except wasmtime.Trap as exc:
            self.store.close()
            if exc.trap_code == wasmtime.TrapCode.INTERRUPT:
                raise InfrastructureError("Initialization watchdog expired") from exc
            raise InitializationError(f"Initialization trap: {exc.trap_code}") from exc
        except wasmtime.WasmtimeError as exc:
            self.store.close()
            raise InitializationError(f"Instantiation failed: {exc}") from exc
        except InitializationError:
            self.store.close()
            raise

    def call(self, observation):
        if len(observation) > 65536:
            raise InfrastructureError("Observation exceeds SDK input region")
        self.memory.write(self.store, observation, self.input_ptr)
        self.store.set_fuel(self.tick_fuel)
        self.store.set_epoch_deadline(200)
        try:
            action = self.exports["arena_tick"](self.store, self.input_ptr, len(observation))
            fault = None if 0 <= action <= 5 else "invalid_action"
            return dict(raw_action=action, fault=fault, fuel_used=self.tick_fuel-self.store.get_fuel())
        except wasmtime.Trap as exc:
            if exc.trap_code == wasmtime.TrapCode.INTERRUPT:
                raise InfrastructureError("Tick watchdog expired") from exc
            fault = "fuel" if exc.trap_code == wasmtime.TrapCode.OUT_OF_FUEL else "trap"
            return dict(raw_action=None, fault=fault, fuel_used=self.tick_fuel-self.store.get_fuel(),
                        trap_code=exc.trap_code.name if exc.trap_code else "UNKNOWN")

    def close(self):
        self.store.close()
