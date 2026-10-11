#pragma once
#include "gomoku.hpp"
#include <algorithm>

namespace plan {
inline int board[225];
inline constexpr int dx[4]={1,0,1,1}, dy[4]={0,1,1,-1};
inline bool inside(int x,int y) { return x>=0 && x<15 && y>=0 && y<15; }
inline int pattern(int i,int color) {
    int x=i%15,y=i/15,value=0;
    for(int d=0;d<4;++d) {
        int n=1,open=0;
        for(int sign: {-1,1}) {
            int nx=x+sign*dx[d],ny=y+sign*dy[d];
            while(inside(nx,ny) && board[ny*15+nx]==color) { ++n; nx+=sign*dx[d]; ny+=sign*dy[d]; }
            if(inside(nx,ny) && !board[ny*15+nx]) ++open;
        }
        if(n>=5) return 10000000;
        if(n==4) value+=open==2?200000:open?20000:0;
        else if(n==3) value+=open==2?8000:open?500:0;
        else if(n==2) value+=open==2?300:open?30:0;
        else value+=open*3;
        // Broken lines such as XX_XX also create immediate threats.
        for(int start=-4;start<=0;++start) {
            int own=0,empty=0;
            for(int k=0;k<5;++k) {
                int nx=x+(start+k)*dx[d],ny=y+(start+k)*dy[d];
                if(!inside(nx,ny)) { own=-10; break; }
                int c=(nx==x && ny==y)?color:board[ny*15+nx];
                if(c==color) ++own; else if(!c) ++empty; else {own=-10;break;}
            }
            if(own==4 && empty==1) value+=10000;
            else if(own==3 && empty==2) value+=200;
        }
    }
    return value;
}
struct Candidate { int i,score; };
inline int candidates(int color,Candidate* out,int limit=8) {
    int n=0;
    for(int i=0;i<225;++i) if(!board[i]) {
        int x=i%15,y=i/15; bool nearby=false;
        for(int oy=-1;oy<=1 && !nearby;++oy) for(int ox=-1;ox<=1;++ox)
            if(inside(x+ox,y+oy) && board[(y+oy)*15+x+ox]) { nearby=true;break; }
        if(!nearby) continue;
        int a=pattern(i,color),b=pattern(i,3-color);
        int score=a*2+b*2-std::abs(x-7)-std::abs(y-7);
        out[n++]={i,score};
    }
    if(!n) { out[0]={112,0};return 1; }
    std::sort(out,out+n,[](Candidate a,Candidate b){ return a.score!=b.score?a.score>b.score:a.i<b.i; });
    return std::min(n,limit);
}
inline void load(const GameState& s) { for(int i=0;i<225;++i) board[i]=s.grid[i]; }
inline int forced(int color) {
    for(int c: {color,3-color}) for(int i=0;i<225;++i)
        if(!board[i] && pattern(i,c)>=10000000) return i;
    return -1;
}
}
