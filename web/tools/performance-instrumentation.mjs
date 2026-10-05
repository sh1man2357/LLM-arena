/** Observe real Canvas draws and native inputs without changing playback scheduling. */
export function instrumentation() {
  const metrics=window.__spectatorPerf={draws:[],seeks:[],firstPaint:null};
  let pending=null,rafTime=null;
  const raf=window.requestAnimationFrame;
  window.requestAnimationFrame=callback=>raf.call(window,time=>{
    const previous=rafTime;rafTime=time;
    try{return callback(time);}finally{rafTime=previous;}
  });
  document.addEventListener('input',e=>{
    if(e.target.matches('input[aria-label="回放帧"]'))pending={input:performance.now(),frame:Number(e.target.value)};
  },true);
  const clear=CanvasRenderingContext2D.prototype.clearRect;
  const arc=CanvasRenderingContext2D.prototype.arc;
  CanvasRenderingContext2D.prototype.arc=function(...args){
    if(this.canvas.matches('.board')&&String(this.strokeStyle).toLowerCase()==='#10151c') {
      const draw=metrics.draws.at(-1);if(draw)draw.player0=args.slice(0,2);
    }
    return arc.apply(this,args);
  };
  CanvasRenderingContext2D.prototype.clearRect=function(...args){
    const result=clear.apply(this,args);
    if(this.canvas.matches('.board')) {
      const started=performance.now(),label=this.canvas.getAttribute('aria-label');
      metrics.draws.push({at:started,label,raf_at:rafTime});
      if(metrics.firstPaint===null) {
        metrics.firstPaint=-1;
        requestAnimationFrame(()=>requestAnimationFrame(()=>{metrics.firstPaint=performance.now();}));
      }
      // SSE can redraw the old board between native input and the React commit.
      // Complete the measurement only when the actual drawn label matches the requested frame.
      if(pending&&label.includes(pending.frame===0?'初始状态':`Tick ${pending.frame-1} 已结算`)) {
        const sample=pending;pending=null;
        requestAnimationFrame(()=>requestAnimationFrame(()=>{
          const frame=Number(document.querySelector('input[aria-label="回放帧"]').value);
          metrics.seeks.push({...sample,paint:performance.now(),frame_at_paint:frame,label});
        }));
      }
    }
    return result;
  };
}

export const quantile=(a,p)=>{const v=[...a].sort((a,b)=>a-b);return v[Math.ceil((v.length-1)*p)]??null;};
export const summary=a=>({count:a.length,min:a.length?Math.min(...a):null,median:quantile(a,.5),p95:quantile(a,.95),max:a.length?Math.max(...a):null});
export function animationStats(draws,elapsed) {
  const groups=[];
  for(const d of draws){let g=groups.at(-1);if(!g||g.label!==d.label)groups.push(g={label:d.label,times:[],positions:[]});g.times.push(d.at);if(d.player0)g.positions.push(d.player0);}
  const measured=groups.filter(g=>g.times.length>=5).map(g=>{
    const times=g.times.filter((t,i)=>!i||t-g.times[i-1]>2);
    const gaps=times.slice(1).map((t,i)=>t-times[i]);
    return {label:g.label,draws:times.length,span_ms:times.at(-1)-times[0],fps:1000*(times.length-1)/(times.at(-1)-times[0]),p95_interval_ms:quantile(gaps,.95)};
  });
  const timestamps=[...new Set(draws.filter(d=>d.raf_at!==null).map(d=>d.raf_at))];
  const reversals=[];
  for(const group of groups)for(const axis of [0,1]) {
    const values=group.positions.map(p=>p[axis]);if(values.length<2)continue;
    const direction=Math.sign(values.at(-1)-values[0]);
    for(let i=1;i<values.length;i++)if((values[i]-values[i-1])*direction<-.05 || (!direction&&Math.abs(values[i]-values[i-1])>.05)) {
      reversals.push({label:group.label,axis,from:values[i-1],to:values[i]});
    }
  }
  return {wall_ms:elapsed,actual_draw_count:draws.length,draws_per_wall_second:draws.length*1000/elapsed,
    actual_animation_frame_draws:timestamps.length,canvas_animation_fps:timestamps.length*1000/elapsed,
    active_animation_fps:summary(measured.map(g=>g.fps)),groups:measured,player0_interpolation_reversals:reversals,
    note:'Canvas FPS counts unique browser animation frames that actually draw the board, over the full playback wall interval including idle gaps. Effect/resize synchronous draws and unrelated RAF callbacks are excluded. Active interpolation FPS is reported separately; compositor presentation is not inferred.'};
}
