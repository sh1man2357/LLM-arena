#include "planner.hpp"
namespace bot {
int nodes;
bool exhausted;
constexpr int NODE_LIMIT=36;
void init(uint64_t) {}
int search(int color,int depth,int alpha,int beta,int last,int balance) {
    if(last>=0 && plan::pattern(last,3-color)>=10000000) return -10000000-depth;
    if(!depth) return balance;
    if(++nodes>NODE_LIMIT) { exhausted=true;return balance; }
    plan::Candidate c[225]; int n=plan::candidates(color,c,6);
    int best=-20000000;
    for(int k=0;k<n;++k) {
        int i=c[k].i, gain=plan::pattern(i,color);
        plan::board[i]=color;
        int score=-search(3-color,depth-1,-beta,-alpha,i,-balance-gain);
        plan::board[i]=0;
        if(exhausted) return best;
        best=std::max(best,score);alpha=std::max(alpha,score); if(alpha>=beta) break;
    }
    return best;
}
Action tick(const GameState& s) {
    plan::load(s); int forced=plan::forced(s.self_color);
    if(forced>=0) return {forced%15,forced/15};
    plan::Candidate roots[225];int n=plan::candidates(s.self_color,roots,8), chosen=roots[0].i;
    nodes=0;exhausted=false;
    for(int depth=1;depth<=4 && !exhausted;++depth) {
        int best=-20000000,pick=chosen;
        for(int k=0;k<n;++k) {
            int i=roots[k].i,gain=plan::pattern(i,s.self_color);
            plan::board[i]=s.self_color;
            int value=-search(3-s.self_color,depth-1,-20000000,-best,i,-gain);
            plan::board[i]=0;
            if(exhausted) break;
            if(value>best) {best=value;pick=i;}
        }
        if(!exhausted) chosen=pick;
    }
    return {chosen%15,chosen/15};
}
}
