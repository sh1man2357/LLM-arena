#pragma once
#include "gomoku.hpp"
#include "patterns.hpp"
#include <algorithm>

namespace champion {
constexpr int WIN=100000000, INF=200000000;
constexpr int dx[4]={1,0,1,1},dy[4]={0,1,1,-1};
constexpr int powers[9]={1,3,9,27,81,243,729,2187,6561};
inline int board[225], lines[3][225][4], value[3][225];
inline uint64_t keys[225][3], hash;
inline int nodes, updates;
inline bool stopped;
struct Entry { uint64_t hash; int score,depth,flag,move; };
inline Entry cache[8192];
inline bool inside(int x,int y) { return x>=0&&x<15&&y>=0&&y<15; }
inline int evaluate(int color,int i) {
    constexpr int weights[8]={0,30,120,900,12000,90000,2000000,WIN};
    int sum=0,fours=0,threes=0;
    for(int d=0;d<4;++d) {
        int type=patterns[lines[color][i][d]];
        if(type==7) return WIN;
        sum+=weights[type];fours+=type>=5;threes+=type==4;
    }
    if(fours>=2 || (fours&&threes)) sum+=1000000;
    else if(threes>=2) sum+=180000;
    return sum;
}
inline void change(int i,int color,bool put) {
    ++updates;board[i]=put?color:0;hash^=keys[i][color];
    int x=i%15,y=i/15,sign=put?1:-1;
    for(int d=0;d<4;++d) for(int k=-4;k<=4;++k) if(k) {
        int nx=x+dx[d]*k,ny=y+dy[d]*k;if(!inside(nx,ny))continue;
        int j=ny*15+nx;
        for(int c=1;c<=2;++c) {
            lines[c][j][d]+=sign*(color==c?1:2)*powers[4-k];
            value[c][j]=evaluate(c,j);
        }
    }
}
inline void load(const GameState& s) {
    hash=0;nodes=updates=0;stopped=false;
    for(int i=0;i<225;++i) {board[i]=s.grid[i];if(board[i])hash^=keys[i][board[i]];}
    for(int i=0;i<225;++i) for(int c=1;c<=2;++c) {
        for(int d=0;d<4;++d) {
            int code=81;
            for(int k=-4;k<=4;++k) if(k) {
                int x=i%15+dx[d]*k,y=i/15+dy[d]*k;
                int v=!inside(x,y)?2:board[y*15+x]==c?1:board[y*15+x]?2:0;
                code+=v*powers[k+4];
            }
            lines[c][i][d]=code;
        }
        value[c][i]=evaluate(c,i);
    }
}
struct Move { int i,score; };
inline int moves(int color,Move* out,int limit,int preferred=-1) {
    int n=0,win=-1,block=-1,blocks=0;
    for(int i=0;i<225;++i) if(!board[i]) {
        int a=value[color][i],b=value[3-color][i];
        if(a>=WIN)win=i;
        if(b>=WIN){block=i;++blocks;}
        int score=std::max(a,b)*2+a+b-std::abs(i%15-7)-std::abs(i/15-7);
        if(i==preferred)score+=3000000;
        if(!n || n<limit || score>out[n-1].score) {
            int pos=std::min(n,limit-1);
            while(pos && (score>out[pos-1].score || (score==out[pos-1].score&&i<out[pos-1].i))) {
                if(pos<limit)out[pos]=out[pos-1];--pos;
            }
            out[pos]={i,score};n=std::min(n+1,limit);
        }
    }
    if(win>=0){out[0]={win,WIN};return 1;}
    if(blocks){out[0]={block,-INF-blocks};return 1;}
    return n;
}
inline int static_score(int color) {
    int a=0,b=0;
    for(int i=0;i<225;++i)if(!board[i]){a=std::max(a,value[color][i]);b=std::max(b,value[3-color][i]);}
    return a-b/2;
}
inline int search(int color,int depth,int alpha,int beta,int ply) {
    if(++nodes>300 || updates>450){stopped=true;return 0;}
    uint64_t key=hash^(color==1?0x9216d5d98979fb1bULL:0x3298a12e5b6db359ULL);
    Entry& hit=cache[key&8191];int preferred=-1,original=alpha;
    if(hit.hash==key) {
        preferred=hit.move;
        if(hit.depth>=depth && (hit.flag==0 || (hit.flag==1&&hit.score>=beta) || (hit.flag==2&&hit.score<=alpha)))return hit.score;
    }
    Move options[8];int n=moves(color,options,depth>=3?6:8,preferred);
    if(!n)return 0;
    int i=options[0].i;
    if(value[color][i]>=WIN)return WIN-ply;
    if(options[0].score<=-INF-2)return -WIN+ply+1;
    if(!depth && options[0].score>-INF)return static_score(color);
    // Extend forced blocks beyond the nominal depth, up to eight plies.
    if(ply>=8)return static_score(color);
    int best=-INF,best_move=i;
    for(int k=0;k<n;++k) {
        i=options[k].i;change(i,color,true);
        int score=-search(3-color,std::max(0,depth-1),-beta,-alpha,ply+1);
        change(i,color,false);
        if(stopped)return 0;
        if(score>best){best=score;best_move=i;}alpha=std::max(alpha,score);
        if(alpha>=beta)break;
    }
    hit={key,best,depth,best<=original?2:best>=beta?1:0,best_move};return best;
}
inline int choose(const GameState& s) {
    load(s);Move roots[10];int color=s.self_color,n=moves(color,roots,10);
    if(!n)return -1;
    int selected=roots[0].i;
    if(value[color][selected]>=WIN || roots[0].score<=-INF)return selected;
    for(int depth=1;depth<=6&&!stopped;++depth) {
        int best=-INF,pick=selected;
        // Search the previous iteration's best move first.
        for(int k=0;k<n;++k)if(roots[k].i==selected)std::swap(roots[0],roots[k]);
        for(int k=0;k<n;++k) {
            int i=roots[k].i;change(i,color,true);
            int score=-search(3-color,depth-1,-INF,-best,1);
            change(i,color,false);
            if(stopped)break;
            if(score>best){best=score;pick=i;}
        }
        if(!stopped){selected=pick;if(best>WIN-20)break;}
    }
    return selected;
}
}
