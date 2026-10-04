#include "arena.hpp"
namespace bot {
void init(uint64_t) {}
Action tick(const GameState&) { return Action::WAIT; }
}
