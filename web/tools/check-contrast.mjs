/** Measure rendered text against its composited ancestor backgrounds. */
export async function contrastReport(page) {
  return page.evaluate(()=>{
    const rgba=value=>{const v=value.match(/[\d.]+/g)?.map(Number)||[0,0,0,0];return v.length===3?[...v,1]:v;};
    const mix=(front,back)=>front.slice(0,3).map((v,i)=>v*front[3]+back[i]*(1-front[3]));
    const lum=rgb=>rgb.slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
    const contrast=(a,b)=>{const x=lum(a),y=lum(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
    const failures=[], rows=[];
    for(const el of document.querySelectorAll('body *')) {
      if(el.closest('svg,canvas,script,style')||el.closest(':disabled')||!el.getClientRects().length)continue;
      const text=[...el.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join('').trim();
      if(!text)continue;
      const ancestors=[];for(let p=el;p;p=p.parentElement)ancestors.unshift(p);
      if(ancestors.some(p=>getComputedStyle(p).visibility==='hidden'||Number(getComputedStyle(p).opacity)<1))continue;
      let background=[16,21,28];for(const p of ancestors)background=mix(rgba(getComputedStyle(p).backgroundColor),background);
      const css=getComputedStyle(el), foreground=mix(rgba(css.color),background);
      const ratio=contrast(foreground,background), large=parseFloat(css.fontSize)>=24||(parseFloat(css.fontSize)>=18.6667&&Number(css.fontWeight)>=700);
      const row={text:text.slice(0,70),element:el.tagName.toLowerCase(),ratio:Number(ratio.toFixed(3)),required:large?3:4.5};
      rows.push(row);if(ratio+1e-6<row.required)failures.push(row);
    }
    const input=document.querySelector('input:not([type="checkbox"]):not([type="range"])');
    const field=input?contrast(rgba(getComputedStyle(input).borderColor),rgba(getComputedStyle(input).backgroundColor)):null;
    const tokens=getComputedStyle(document.documentElement);
    const hex=value=>value.trim().slice(1).match(/.{2}/g).map(v=>parseInt(v,16));
    const terrain=['--tile-hard','--tile-soft'].map(name=>({name,ratio:Number(contrast(hex(tokens.getPropertyValue(name)),[23,33,41]).toFixed(3))}));
    return{tested:rows.length,minimum:rows.reduce((a,b)=>a.ratio<b.ratio?a:b,{ratio:Infinity}),failures,field_boundary_ratio:field,terrain};
  });
}
