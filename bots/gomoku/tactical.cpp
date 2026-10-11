#include "planner.hpp"
namespace bot {
void init(uint64_t) {}
Action tick(const GameState& s) {
    plan::load(s); int i=plan::forced(s.self_color);
    if(i<0) { plan::Candidate c[225];plan::candidates(s.self_color,c);i=c[0].i; }
    return {i%15,i/15};
}
}
