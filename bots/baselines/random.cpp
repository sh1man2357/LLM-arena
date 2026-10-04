#include "arena.hpp"
static arena::Rng rng;
namespace bot {
void init(uint64_t seed) { rng.seed(seed); }
Action tick(const GameState&) { return Action(rng.next() % 6); }
}
