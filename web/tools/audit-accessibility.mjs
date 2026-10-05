/** Actual rendered DOM, computed contrast, keyboard and reduced-motion audit. */
import {chromium, expect} from '@playwright/test';
import {mkdirSync, writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
const [base='http://127.0.0.1:8861',out='../artifacts/acceptance/v0.2-development/final'] = process.argv.slice(2);
const output=resolve(out); mkdirSync(resolve(output,'checks'),{recursive:true});mkdirSync(resolve(output,'visual'),{recursive:true});
const browser=await chromium.launch({channel:'chrome'}),context=await browser.newContext({baseURL:base});
const page=await context.newPage(), reports=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
try {
  for(const width of [390,768,1280,1440])for(const [name,path,ready] of [
    ['hall','/','.feature-board canvas'],['viewer','/matches/reference-chain?frame=13','canvas'],
    ['batch','/tournaments/reference-v01','.ranking-row'],['entrants','/entrants','.entrant-card'],
    ['entrant','/entrants/safe','.identity-panel'],['manage','/manage','.workflow-grid input']]) {
    await page.setViewportSize({width,height:1000});await page.goto(path);await expect(page.locator(ready).first()).toBeVisible();
    await expect(page.getByText('本地服务已连接',{exact:true})).toBeVisible();
    if(name==='hall')await expect(page.locator('.match-row').first()).toBeVisible();
    if(name==='viewer')await expect(page.getByRole('slider',{name:'回放帧'})).toHaveValue('13');
    if(name==='batch') {await expect(page.locator('.draw-analysis')).toBeVisible();await expect(page.locator('.match-row')).toHaveCount(100);}
    if(name==='entrant')await expect(page.locator('.match-row')).toHaveCount(100);
    if(name==='manage')await expect(page.getByRole('heading',{name:'正在读取工作台记录'})).toHaveCount(0);
    await page.evaluate(()=>document.fonts.ready);
    const audit=await page.evaluate(()=>{
      const rgba=s=>{const m=s.match(/[\d.]+/g);return m ? m.map(Number) : [0,0,0,0]};
      const over=(f,b)=>[0,1,2].map(i=>f[i]*(f[3]??1)+b[i]*(1-(f[3]??1)));
      const luminance=c=>c.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((v,c,i)=>v+c*[.2126,.7152,.0722][i],0);
      const contrast=(f,b)=>{const a=luminance(f),z=luminance(b);return(Math.max(a,z)+.05)/(Math.min(a,z)+.05)};
      const background=e=>{const chain=[];for(let p=e;p;p=p.parentElement)chain.push(p);let bg=[255,255,255];for(const p of chain.reverse())bg=over(rgba(getComputedStyle(p).backgroundColor),bg);return bg;};
      const visible=e=>e.getClientRects().length && getComputedStyle(e).visibility!=='hidden' && !e.closest('[hidden],details:not([open]) > :not(summary)');
      const text=[];for(const e of document.querySelectorAll('body *')) {
        if(!visible(e)||e.closest('svg,canvas,option,script,style')||e.closest(':disabled'))continue;
        const direct=[...e.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join('').trim();if(!direct)continue;
        const s=getComputedStyle(e),bg=background(e),ratio=contrast(over(rgba(s.color),bg),bg);
        const large=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&parseInt(s.fontWeight)>=700);
        text.push({text:direct.slice(0,75),selector:e.tagName+'.'+e.className,ratio,required:large?3:4.5,color:s.color,background:bg});
      }
      const controls=[...document.querySelectorAll('button,input,select,textarea,a[href],summary')].filter(visible).map(e=>{
        const r=e.getBoundingClientRect(),label=e.closest('label');const hit=label?.getBoundingClientRect()||r;
        const name=e.getAttribute('aria-label')||e.textContent?.trim()||e.labels?.[0]?.textContent?.trim()||e.title||'';
        return {tag:e.tagName,type:e.type,name:name.slice(0,100),width:hit.width,height:hit.height,disabled:!!e.disabled,primary:e.matches('button,.button,input,select,textarea,summary')};
      });
      return {text,controls,overflow:document.documentElement.scrollWidth>innerWidth,live_regions:[...document.querySelectorAll('[aria-live]')].map(e=>({live:e.getAttribute('aria-live'),text:e.textContent.slice(0,100)}))};
    });
    reports.push({name,path,width,...audit,violations:audit.text.filter(x=>x.ratio+.01<x.required),small_controls:audit.controls.filter(x=>x.primary&&!x.disabled&&(x.width<43.9||x.height<43.9)),unnamed:audit.controls.filter(x=>!x.name&&x.type!=='file')});
    writeFileSync(resolve(output,'visual',`${name}-${width}-accessibility.txt`),await page.locator('main').ariaSnapshot());
  }
  await page.setViewportSize({width:1280,height:1000});await page.goto('/matches/reference-chain');await expect(page.locator('canvas')).toBeVisible();
  await page.keyboard.press('Tab');await expect(page.getByRole('link',{name:'跳到主要内容'})).toBeFocused();
  const focus=await page.getByRole('link',{name:'跳到主要内容'}).evaluate(e=>({outline:getComputedStyle(e).outline,rect:e.getBoundingClientRect().toJSON()}));
  await page.keyboard.press('Enter');await page.locator('body').click({position:{x:1000,y:500}});
  await page.keyboard.press('End');await expect(page.getByRole('slider',{name:'回放帧'})).toHaveValue('19');
  await page.keyboard.press('Home');await expect(page.getByRole('slider',{name:'回放帧'})).toHaveValue('0');
  await page.keyboard.press('Space');await expect(page.getByRole('button',{name:'暂停 (Space)',exact:true})).toBeVisible();
  await page.keyboard.press('Space');await expect(page.getByRole('button',{name:'播放 (Space)',exact:true})).toBeVisible();
  const focusControls=[];
  for(const label of ['播放 (Space)','播放速度','回放帧']){
    const control=page.getByLabel(label,{exact:true});await control.focus();
    const measured=await control.evaluate(e=>({name:e.getAttribute('aria-label'),width:parseFloat(getComputedStyle(e).outlineWidth),style:getComputedStyle(e).outlineStyle}));
    expect(measured.style).toBe('solid');expect(measured.width).toBeGreaterThanOrEqual(2);focusControls.push(measured);
  }
  await page.getByRole('button',{name:'格子',exact:true}).click();await page.getByLabel('格子 x',{exact:true}).fill('5');await page.getByLabel('格子 y',{exact:true}).fill('3');
  await expect(page.locator('.inspector-card h2')).toHaveText('5, 3');await page.keyboard.press('ArrowRight');await expect(page.getByRole('slider',{name:'回放帧'})).toHaveValue('0');
  await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/matches/reference-chain?frame=1');await expect(page.getByRole('slider',{name:'回放帧'})).toHaveValue('1');
  const first=await page.locator('canvas').evaluate(e=>e.toDataURL());await page.waitForTimeout(220);const last=await page.locator('canvas').evaluate(e=>e.toDataURL());expect(first).toBe(last);
  writeFileSync(resolve(output,'checks/accessibility.json'),JSON.stringify({status:reports.some(r=>r.violations.length||r.small_controls.length||r.unnamed.length||r.overflow)?'needs-fixes':'passed',reports,keyboard:{skip_focus:focus,first_last:true,space_toggles:true,visible_control_focus:focusControls,coordinate_equivalent:true,input_does_not_seek:true},reduced_motion:{media:true,static_frame_unchanged:true},page_errors:errors},null,2)+'\n');
  console.log(JSON.stringify(reports.filter(r=>r.violations.length||r.small_controls.length||r.unnamed.length).map(r=>({name:r.name,width:r.width,violations:r.violations,small:r.small_controls,unnamed:r.unnamed}))));
} finally {await context.close();await browser.close();}
