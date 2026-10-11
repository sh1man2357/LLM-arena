#pragma once
#include "gomoku.hpp"
#include "patterns.hpp"
#include <algorithm>

namespace champion {
constexpr int WIN=100000000, INF=200000000, TABLE=32768;
constexpr int dx[4]={1,0,1,1},dy[4]={0,1,1,-1};
constexpr int powers[9]={1,3,9,27,81,243,729,2187,6561};
constexpr int weights[8]={0,30,120,900,12000,90000,2000000,WIN};
inline int board[225],lines[3][225][4],value[3][225];
inline int total[3][225],fours[3][225],threes[3][225],wins[3][225];
inline uint64_t keys[225][3],hash;
inline int nodes,updates,work,history[3][225],killers[20][2];
inline bool stopped;
// Meter scans, sorting and incremental updates rather than limiting cheap nodes.
constexpr int WORK_LIMIT=12000000,PROOF_LIMIT=3500000;
struct Entry {uint64_t hash;int score,depth,flag,move;};
inline Entry cache[TABLE];
struct Move {int i,score;};
inline bool inside(int x,int y){return x>=0&&x<15&&y>=0&&y<15;}
inline int point(int c,int i){
    if(wins[c][i])return WIN;
    int score=total[c][i];
    if(fours[c][i]>=2||(fours[c][i]&&threes[c][i]))score+=1000000;
    else if(threes[c][i]>=2)score+=180000;
    return score;
}
inline void change(int i,int color,bool put){
    ++updates;work+=160;board[i]=put?color:0;hash^=keys[i][color];
    int x=i%15,y=i/15,sign=put?1:-1;
    for(int d=0;d<4;++d)for(int k=-4;k<=4;++k)if(k){
        int nx=x+dx[d]*k,ny=y+dy[d]*k;work+=18;if(!inside(nx,ny))continue;
        int j=ny*15+nx;
        for(int c=1;c<=2;++c){
            int before=patterns[lines[c][j][d]];
            lines[c][j][d]+=sign*(color==c?1:2)*powers[4-k];
            int after=patterns[lines[c][j][d]];work+=95;
            if(before==after)continue;
            total[c][j]+=weights[after]-weights[before];
            fours[c][j]+=(after>=5)-(before>=5);
            threes[c][j]+=(after==4)-(before==4);
            wins[c][j]+=(after==7)-(before==7);
            value[c][j]=point(c,j);work+=105;
        }
    }
}
inline int digit(int x,int y,int c){
    return !inside(x,y)?2:board[y*15+x]==c?1:board[y*15+x]?2:0;
}
inline void load(const GameState& s){
    hash=0;nodes=updates=work=0;stopped=false;
    for(int i=0;i<225;++i){board[i]=s.grid[i];if(board[i])hash^=keys[i][board[i]];}
    // Roll nine-cell windows, then replace the center with the candidate stone.
    for(int c=1;c<=2;++c)for(int d=0;d<4;++d)
        for(int y=0;y<15;++y)for(int x=0;x<15;++x){
            if(inside(x-dx[d],y-dy[d]))continue;
            int code=0;
            for(int k=-4;k<=4;++k)code+=digit(x+dx[d]*k,y+dy[d]*k,c)*powers[k+4];
            int nx=x,ny=y;
            while(inside(nx,ny)){
                int i=ny*15+nx;
                lines[c][i][d]=code+(1-digit(nx,ny,c))*81;
                code=code/3+digit(nx+dx[d]*5,ny+dy[d]*5,c)*6561;
                nx+=dx[d];ny+=dy[d];
            }
        }
    for(int c=1;c<=2;++c)for(int i=0;i<225;++i){
        total[c][i]=fours[c][i]=threes[c][i]=wins[c][i]=0;
        for(int d=0;d<4;++d){
            int type=patterns[lines[c][i][d]];
            total[c][i]+=weights[type];fours[c][i]+=type>=5;
            threes[c][i]+=type==4;wins[c][i]+=type==7;
        }
        value[c][i]=point(c,i);history[c][i]/=2;
    }
    for(auto& k:killers)k[0]=k[1]=-1;
    work=650000;
}
inline void insert(Move* out,int& n,int limit,int i,int score){
    work+=15;if(n==limit&&score<=out[n-1].score)return;
    int pos=std::min(n,limit-1);
    while(pos&&(score>out[pos-1].score||(score==out[pos-1].score&&i<out[pos-1].i))){
        out[pos]=out[pos-1];--pos;work+=20;
    }
    out[pos]={i,score};n=std::min(n+1,limit);
}
inline int moves(int c,Move* out,int limit,int preferred=-1,int ply=0,bool forcing=false){
    int n=0,win=-1,block=-1,blocks=0;
    for(int i=0;i<225;++i){
        work+=8;if(board[i])continue;
        int a=value[c][i],b=value[3-c][i];work+=35;
        if(a>=WIN)win=i;if(b>=WIN){block=i;++blocks;}
        if(forcing&&!fours[c][i])continue;
        int score=std::max(a,b)*2+a+b-abs(i%15-7)-abs(i/15-7)+history[c][i]/32;
        if(i==preferred)score+=4000000;
        if(ply<20&&(i==killers[ply][0]||i==killers[ply][1]))score+=8000;
        insert(out,n,limit,i,score);
    }
    if(win>=0){out[0]={win,WIN};return 1;}
    if(blocks){out[0]={block,-INF-blocks};return 1;}
    return n;
}
inline int static_score(int c){
    int top[3][3]{};
    for(int i=0;i<225;++i){
        work+=8;if(board[i])continue;
        for(int p=1;p<=2;++p){
            int v=value[p][i];
            for(int k=0;k<3;++k)if(v>top[p][k])std::swap(v,top[p][k]);
            work+=35;
        }
    }
    // Discount the opponent's threats because the side to move has initiative.
    int a=top[c][0]+top[c][1]/4+top[c][2]/16;
    int b=top[3-c][0]+top[3-c][1]/4+top[3-c][2]/16;
    return a-b/2;
}
// Prove continuous-four wins by checking every forced reply.
// Reaching a work/depth limit is never treated as a proof.
inline bool prove(int c,int depth,int& first,int cap=PROOF_LIMIT){
    if(work>cap||depth<=0)return false;
    ++nodes;Move options[12];int n=moves(c,options,12,-1,0,true);
    if(!n)return false;
    if(value[c][options[0].i]>=WIN){first=options[0].i;return true;}
    if(options[0].score<=-INF){
        if(options[0].score<=-INF-2||!fours[c][options[0].i])return false;
    }
    for(int k=0;k<n&&work<=cap;++k){
        int i=options[k].i;change(i,c,true);
        int winning=0,reply=-1;bool counter=false;
        for(int j=0;j<225;++j){
            work+=10;if(board[j])continue;work+=12;
            counter|=value[3-c][j]>=WIN;
            if(value[c][j]>=WIN){reply=j;++winning;}
        }
        bool proven=!counter&&winning>=2;
        if(!counter&&winning==1&&depth>=3&&work<=cap){
            change(reply,3-c,true);int continuation=-1;
            proven=prove(c,depth-2,continuation,cap);change(reply,3-c,false);
        }
        change(i,c,false);
        if(proven){first=i;return true;}
    }
    return false;
}
// Two open threes on different axes cannot both be blocked by one stone.
// The defender can instead counter with a four, so verify every such counter.
inline bool prove_threes(int c,int& first,int cap){
    Move options[16];int n=moves(c,options,16);
    for(int k=0;k<n&&work<cap;++k){
        int i=options[k].i;
        if(threes[c][i]<2)continue;
        int local_cap=std::min(work+250000,cap);
        change(i,c,true);bool proven=true;
        for(int j=0;j<225&&proven;++j){
            work+=22;if(board[j]||!fours[3-c][j])continue;
            if(value[3-c][j]>=WIN||work>=local_cap){proven=false;break;}
            change(j,3-c,true);int reply=-1;
            proven=prove(c,13,reply,local_cap);change(j,3-c,false);
        }
        change(i,c,false);
        if(proven&&work<local_cap){first=i;return true;}
    }
    return false;
}
inline bool proof(int c,int& first,int cap){
    return prove_threes(c,first,cap)||prove(c,13,first,cap);
}
inline int store_mate(int score,int ply){
    return score>WIN-1000?score+ply:score<-WIN+1000?score-ply:score;
}
inline int read_mate(int score,int ply){
    return score>WIN-1000?score-ply:score<-WIN+1000?score+ply:score;
}
inline int search(int c,int depth,int alpha,int beta,int ply){
    if(work>WORK_LIMIT){stopped=true;return 0;}++nodes;
    uint64_t key=hash^(c==1?0x9216d5d98979fb1bULL:0x3298a12e5b6db359ULL);
    Entry& hit=cache[key&(TABLE-1)];int preferred=-1,original=alpha;
    if(hit.hash==key){
        preferred=hit.move;int v=read_mate(hit.score,ply);
        if(depth>0&&hit.depth>=depth&&(hit.flag==0||(hit.flag==1&&v>=beta)||(hit.flag==2&&v<=alpha)))return v;
    }
    Move options[12];int n=moves(c,options,depth>=3?6:8,preferred,ply);
    if(!n)return 0;
    int i=options[0].i;
    if(value[c][i]>=WIN)return WIN-ply;
    if(options[0].score<=-INF-2)return -WIN+ply+1;
    bool forced=options[0].score<=-INF;
    // Making an open four wins on the following move. Immediate counterwins
    // have already forced the only block above, so this is a proven shortcut.
    for(int k=0;k<n;++k)if(value[c][options[k].i]>=2000000)return WIN-ply-2;
    if(ply>=16)return static_score(c);
    if(depth<=0&&!forced){
        bool fork=false;
        for(int k=0;k<n;++k)fork|=threes[c][options[k].i]>=2;
        if(fork&&work<WORK_LIMIT-500000){
            int first=-1;
            if(prove_threes(c,first,std::min(work+150000,WORK_LIMIT-300000)))return WIN-ply-3;
        }
        return static_score(c);
    }
    int best=-INF,best_move=i;
    for(int k=0;k<n;++k){
        i=options[k].i;
        bool reduce=depth>=3&&k>=4&&!forced&&value[c][i]<12000&&value[3-c][i]<12000;
        change(i,c,true);int score;
        int next=std::max(0,depth-1);
        if(k==0)score=-search(3-c,next,-beta,-alpha,ply+1);
        else{
            score=-search(3-c,std::max(0,next-int(reduce)),-alpha-1,-alpha,ply+1);
            if(!stopped&&score>alpha&&(score<beta||reduce))score=-search(3-c,next,-beta,-alpha,ply+1);
        }
        change(i,c,false);if(stopped)return 0;
        if(score>best){best=score;best_move=i;}alpha=std::max(alpha,score);
        if(alpha>=beta){
            if(ply<20&&killers[ply][0]!=i){killers[ply][1]=killers[ply][0];killers[ply][0]=i;}
            history[c][i]=std::min(1000000,history[c][i]+depth*depth*100);break;
        }
    }
    if(depth>0)hit={key,store_mate(best,ply),depth,best<=original?2:best>=beta?1:0,best_move};
    return best;
}
inline int choose(const GameState& s){
    load(s);Move roots[16];int c=s.self_color,n=moves(c,roots,16);
    if(!n)return -1;int selected=roots[0].i;
    if(value[c][selected]>=WIN||roots[0].score<=-INF)return selected;
    int proven=-1;if(proof(c,proven,PROOF_LIMIT))return proven;
    // Search the opponent's continuous-four attack before trusting a quiet score.
    // A lower-ranked defensive point can be the only move that breaks the whole chain.
    int incoming=-1;
    if(proof(3-c,incoming,std::min(work+1000000,WORK_LIMIT-4000000))){
        Move defended[16];int safe_count=0;
        int cap=std::min(work+3500000,WORK_LIMIT-2000000);
        for(int k=0;k<n;++k){
            int i=roots[k].i;change(i,c,true);int reply=-1;
            bool lost=proof(3-c,reply,std::min(work+300000,cap));
            change(i,c,false);
            if(!lost)defended[safe_count++]=roots[k];
        }
        if(safe_count){
            n=safe_count;for(int k=0;k<n;++k)roots[k]=defended[k];
            selected=roots[0].i;
        }
    }
    for(int depth=1;depth<=10&&!stopped;++depth){
        int best=-INF,pick=selected;
        for(int k=0;k<n;++k)if(roots[k].i==selected)std::swap(roots[0],roots[k]);
        for(int k=0;k<n;++k){
            int i=roots[k].i;change(i,c,true);
            int score=-search(3-c,depth-1,-INF,-best,1);change(i,c,false);
            if(stopped)break;if(score>best){best=score;pick=i;}
        }
        if(!stopped){selected=pick;if(best>WIN-30)break;}
    }
    return selected;
}
}
