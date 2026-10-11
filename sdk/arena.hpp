#pragma once
#include <cstdint>

namespace arena {
enum class Action : uint32_t { WAIT, UP, RIGHT, DOWN, LEFT, BOMB };
enum Terrain : uint8_t { FLOOR, HARD_WALL, SOFT_WALL };
struct Player { uint32_t id, x, y, alive, score, kills; };
struct Bomb { uint32_t id, owner_id, x, y, explode_at_tick, range; };
struct GameState {
    uint32_t tick, width, height, self_id, player_count, bomb_count;
    uint32_t max_ticks, bomb_fuse_ticks, bomb_capacity, blast_range;
    uint32_t scoring_version, survival_points, kill_points;
    uint8_t grid[31 * 31];
    Player players[8];
    Bomb bombs[8];
    const Player& self() const { return players[self_id]; }
    bool inside(int x, int y) const { return x >= 0 && y >= 0 && x < int(width) && y < int(height); }
    uint8_t cell(int x, int y) const { return inside(x, y) ? grid[y * width + x] : HARD_WALL; }
};
// xorshift64*: seed 0 has a fixed substitute; all operations are unsigned.
struct Rng {
    uint64_t state = 1;
    void seed(uint64_t value) { state = value ? value : 0x9e3779b97f4a7c15ULL; }
    uint32_t next() {
        state ^= state >> 12; state ^= state << 25; state ^= state >> 27;
        return uint32_t((state * 2685821657736338717ULL) >> 32);
    }
};
}

using arena::Action;
using arena::GameState;
namespace bot {
void init(uint64_t seed);
Action tick(const GameState& state);
}
