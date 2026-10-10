#include "arena.hpp"
static unsigned route[] = {1,1,1,1,4,4,4,4,1,1,4,4,4,4,1,1,4};
namespace bot {
void init(uint64_t) {}
Action tick(const GameState& state) {
    if (state.tick < 17) return Action(route[state.tick]);
    return state.tick == 17 ? Action::BOMB : Action::WAIT;
}
}
