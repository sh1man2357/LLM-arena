#include "arena.hpp"
namespace bot {
void init(uint64_t) {}
Action tick(const GameState& state) {
    return state.tick == 14 ? Action::BOMB : Action::WAIT;
}
}
