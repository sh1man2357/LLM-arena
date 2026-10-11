#include "gomoku.hpp"
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
extern "C" int32_t arena_tick(uint32_t ptr, uint32_t size) {
    if (ptr != arena_input_ptr() || size != 273) __builtin_trap();
    const uint8_t* p = input;
    if (read32(p) != 0x314d4f47 || read32(p+4) != 1) __builtin_trap();
    state.width=read32(p+8); state.height=read32(p+12); state.self_id=read32(p+16);
    state.self_color=read32(p+20); state.turn_color=read32(p+24); state.move_count=read32(p+28);
    state.last_x=int32_t(read32(p+32)); state.last_y=int32_t(read32(p+36));
    state.move_fuel=read32(p+40); state.win_length=read32(p+44);
    if(state.width!=15 || state.height!=15 || state.self_id>1 || state.self_color!=state.self_id+1 ||
       state.turn_color!=state.self_color || state.move_count>=225 || state.win_length!=5) __builtin_trap();
    for(int i=0;i<225;++i) { if(p[48+i]>2) __builtin_trap(); state.grid[i]=p[48+i]; }
    Action a=bot::tick(state);
    if(a.x==-1 && a.y==-1) return 225;
    if(a.x<0 || a.x>=15 || a.y<0 || a.y>=15) return -1;
    return a.y*15+a.x;
}
