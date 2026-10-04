#include "arena.hpp"
#include <cstdlib>
#include <new>
#include <__verbose_abort>

// libc++ failure diagnostics must trap locally instead of importing stderr I/O.
_LIBCPP_BEGIN_NAMESPACE_STD
[[noreturn]] void __libcpp_verbose_abort(const char*, ...) noexcept { __builtin_trap(); }
_LIBCPP_END_NAMESPACE_STD

// Keep heap allocation within linear memory; allocation failure is a local trap.
void* operator new(std::size_t size) {
    void* p=std::malloc(size?size:1); if(!p)__builtin_trap(); return p;
}
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p,std::size_t) noexcept { std::free(p); }
void operator delete[](void* p,std::size_t) noexcept { std::free(p); }
void* operator new(std::size_t size,const std::nothrow_t&) noexcept { return std::malloc(size?size:1); }
void* operator new[](std::size_t size,const std::nothrow_t& n) noexcept { return ::operator new(size,n); }
void operator delete(void* p,const std::nothrow_t&) noexcept { std::free(p); }
void operator delete[](void* p,const std::nothrow_t&) noexcept { std::free(p); }

alignas(16) static uint8_t input[65536];
static GameState state;
extern "C" void __wasm_call_ctors();
extern "C" void abort() { __builtin_trap(); }

static uint32_t read32(const uint8_t* p) {
    return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
extern "C" uint32_t arena_input_ptr() { return uint32_t(uintptr_t(input)); }
extern "C" void arena_init(uint32_t lo, uint32_t hi) {
    __wasm_call_ctors();
    bot::init(uint64_t(lo) | uint64_t(hi) << 32);
}
extern "C" uint32_t arena_tick(uint32_t ptr, uint32_t size) {
    if (ptr != arena_input_ptr() || size < 48) __builtin_trap();
    const uint8_t* p = input;
    if (read32(p) != 1) __builtin_trap();
    state.tick=read32(p+4); state.width=read32(p+8); state.height=read32(p+12);
    state.self_id=read32(p+16); state.player_count=read32(p+20); state.bomb_count=read32(p+24);
    uint32_t cells=read32(p+28);
    state.max_ticks=read32(p+32); state.bomb_fuse_ticks=read32(p+36);
    state.bomb_capacity=read32(p+40); state.blast_range=read32(p+44);
    if (state.width == 0 || state.height == 0 || state.width > 31 || state.height > 31 ||
        state.player_count < 2 || state.player_count > 8 || state.bomb_count > 8 ||
        state.self_id >= state.player_count || cells != state.width * state.height ||
        size != 48 + cells + 16 * state.player_count + 24 * state.bomb_count) __builtin_trap();
    p += 48;
    for (uint32_t i=0; i<cells; ++i) state.grid[i]=*p++;
    for (uint32_t i=0; i<state.player_count; ++i) {
        state.players[i] = {read32(p),read32(p+4),read32(p+8),read32(p+12)}; p += 16;
    }
    for (uint32_t i=0; i<state.bomb_count; ++i) {
        state.bombs[i] = {read32(p),read32(p+4),read32(p+8),read32(p+12),read32(p+16),read32(p+20)}; p += 24;
    }
    return uint32_t(bot::tick(state));
}
