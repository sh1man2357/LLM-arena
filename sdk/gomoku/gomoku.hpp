#pragma once
#include <cstdint>

namespace gomoku {
constexpr int SIZE = 15;
enum Cell : uint8_t { EMPTY = 0, BLACK = 1, WHITE = 2 };
struct Action {
    int32_t x, y;
    static Action resign() { return {-1, -1}; }
};
struct GameState {
    uint32_t width, height, self_id, self_color, turn_color, move_count, move_fuel, win_length;
    int32_t last_x, last_y;
    uint8_t grid[SIZE * SIZE];
    bool inside(int x, int y) const { return x >= 0 && y >= 0 && x < SIZE && y < SIZE; }
    uint8_t cell(int x, int y) const { return inside(x,y) ? grid[y*SIZE+x] : 3; }
};
struct Rng {
    uint64_t state = 1;
    void seed(uint64_t value) { state = value ? value : 0x9e3779b97f4a7c15ULL; }
    uint32_t next() {
        state ^= state >> 12; state ^= state << 25; state ^= state >> 27;
        return uint32_t((state * 2685821657736338717ULL) >> 32);
    }
};
}
using gomoku::Action;
using gomoku::GameState;
namespace bot {
void init(uint64_t seed);
Action tick(const GameState& state);
}
