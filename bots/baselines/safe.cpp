#include "planner.hpp"
static arena::Rng rng;
namespace bot {
void init(uint64_t seed) { rng.seed(seed); }
Action tick(const GameState& s) {
    auto f=planning::forecast(s,false);
    int move=planning::plan(s,f,false,rng);
    return move<0?Action::WAIT:Action(move);
}
}
