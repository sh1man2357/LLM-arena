#include "champion.hpp"
static arena::Rng rng;
namespace bot {
void init(uint64_t seed) {
    rng.seed(seed);champion::previous=champion::older=-1;
    champion::stamp=champion::stationary=0;
    for(auto& t:champion::last_visit)t=0;
}
Action tick(const GameState& s) { return Action(champion::choose(s,rng)); }
}
