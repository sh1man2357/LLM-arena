/** Native browser controls and actual WASM/rules traces, with rendered evidence. */
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { contrastReport } from './check-contrast.mjs';

const [base='http://127.0.0.1:8799', outputArg='../artifacts/acceptance/v0.2-development'] = process.argv.slice(2);
const output=resolve(outputArg), visual=resolve(output, 'visual/viewer-quality');
mkdirSync(visual, { recursive: true });
process.env.PLAYWRIGHT_BROWSERS_PATH ||= resolve(fileURLToPath(new URL('../..',import.meta.url)),'.tools/playwright');
const { chromium, expect } = await import('@playwright/test');
const browser=await chromium.launch({channel:'chrome', headless:true});
let context;
try {
context=await browser.newContext({baseURL:base, viewport:{width:1280,height:1000}, recordVideo:{dir:visual,size:{width:1280,height:1000}}});
const page=await context.newPage(), errors=[], checks=[], snapshots=[], contrasts=[];
page.on('pageerror', error=>errors.push(error.message));
const slider=()=>page.getByRole('slider',{name:'回放帧'});
const api=async id=>{
  const response=await context.request.get(`/api/v1/matches/${id}/frames`);
  expect(response.ok()).toBeTruthy(); return response.json();
};
async function open(id, frame=0) {
  await page.goto(`/matches/${id}?frame=${frame}`);
  await expect(page.locator('canvas')).toBeVisible();
  await expect(slider()).toHaveValue(String(frame));
}
async function screenshot(name) {
  await page.screenshot({path:resolve(visual, `${name}.png`),fullPage:true}); snapshots.push(`${name}.png`);
}
async function pixels(frame) {
  const result=await page.locator('canvas').evaluate((canvas, state)=>{
    const ctx=canvas.getContext('2d'), cell=canvas.width/13;
    const entities=[...state.state.players,...state.state.bombs];
    const expected=new Set(state.visual.coverage.map(p=>`${p.x},${p.y}`));
    const mismatches=[];
    for(let y=0;y<11;y++) for(let x=0;x<13;x++) {
      if(entities.some(p=>p.x===x&&p.y===y))continue;
      const rgb=Array.from(ctx.getImageData(Math.floor((x+.5)*cell),Math.floor((y+.5)*cell),1,1).data);
      const blast=rgb[0]===255&&rgb[1]===226&&rgb[2]===170;
      if(blast!==expected.has(`${x},${y}`))mismatches.push({x,y,rgb});
    }
    return mismatches;
  },frame);
  expect(result).toEqual([]);
}
  for(const id of ['viewer-init-both','viewer-init-one']) {
    const data=await api(id); expect(data.frames).toHaveLength(1); expect(data.result.ticks).toBe(0);
    await open(id);
    await expect(page.locator('.versus-player').filter({hasText:'初始化淘汰'})).toHaveCount(id.endsWith('both')?2:1);
    await expect(page.getByText('初始化失败，结算前淘汰',{exact:true})).toBeVisible();
    await expect(page.locator('.inspector-card')).toContainText('初始化未完成');
    await expect(page.getByText(/Tick -1/)).toHaveCount(0);
    await expect(page.locator('.result-banner')).toContainText('初始化结束 · 0 次结算');
    await expect(slider()).toBeDisabled(); await screenshot(id);
    checks.push({id,frames:1,zero_tick:true});
  }
  for(const [id,label,ticks] of [['viewer-fuel','fuel 耗尽',3],['viewer-invalid','非法动作',3],['viewer-trap','运行崩溃',1]]) {
    const data=await api(id); expect(data.result.ticks).toBe(ticks); expect(data.result.valid).toBeTruthy();
    await open(id,ticks);
    await expect(page.locator('.inspector-card .badge')).toContainText(label);
    await expect(page.locator('.event-list')).toContainText('运行故障');
    if(id==='viewer-trap')await expect(page.locator('.event-row strong').filter({hasText:'运行崩溃'})).toHaveCount(1);
    await expect(page.locator('.result-banner')).toContainText('获胜');
    await screenshot(id); checks.push({id,fault:label,ticks});
  }
  await open('viewer-infra',3);
  await expect(page.locator('.result-banner')).toContainText('对局运行失败');
  await expect(page.locator('.result-banner')).toContainText('基础设施失败');
  expect(await page.getByText(/获胜$/).count()).toBe(0); await screenshot('viewer-infra');
  checks.push({id:'viewer-infra',no_formal_winner:true});
  const blocked=await api('viewer-blocked'); await open('viewer-blocked',1);
  expect(blocked.frames[1].state.players[0]).toEqual(blocked.frames[0].state.players[0]);
  await expect(page.locator('.inspector-card')).toContainText('本 Tick 移动未成功');
  await expect(page.locator('.inspector-card')).toContainText('0 / 0'); await pixels(blocked.frames[1]);
  checks.push({id:'viewer-blocked',position_unchanged:true,no_action_fault:true});
  const escape=await api('viewer-escape'); await open('viewer-escape',1);
  await page.getByRole('button',{name:'格子',exact:true}).click();
  await page.getByLabel('格子 x').fill('1'); await page.getByLabel('格子 y').fill('1');
  await expect(page.locator('.bomb-info')).toContainText('Tick 4 到期');
  await expect(page.locator('.bomb-info')).toContainText('剩余 3 Tick');
  await open('viewer-escape',4); await page.getByRole('button',{name:'格子',exact:true}).click();
  await page.getByLabel('格子 x').fill('1'); await page.getByLabel('格子 y').fill('1');
  await expect(page.locator('.bomb-info')).toContainText('剩余 0 Tick');
  await open('viewer-escape',5); await pixels(escape.frames[5]); await screenshot('viewer-explosion');
  await expect(page.getByRole('region',{name:'当前 Tick 爆炸事实'})).toContainText('原定 Tick 4 到期');
  await open('viewer-escape',6); await pixels(escape.frames[6]);
  await expect(page.getByRole('region',{name:'当前 Tick 爆炸事实'})).toHaveCount(0);
  checks.push({id:'viewer-escape',t_plus_4:true,no_lingering_fire:true});
  for(const id of ['viewer-new-chain','viewer-dead-owner']) {
    const data=await api(id), frame=data.frames.at(-1); await open(id,frame.seq);
    const facts=page.getByRole('region',{name:'当前 Tick 爆炸事实'});
    await expect(facts.locator('.explosion-fact')).toHaveCount(frame.visual.exploded_bombs.length);
    for(const bomb of frame.visual.exploded_bombs) {
      const row=facts.locator(`[data-bomb-id="${bomb.id}"]`);
      await expect(row).toContainText(`${bomb.x}, ${bomb.y}`);
      await expect(row).toContainText(`原定 Tick ${bomb.explode_at_tick} 到期`);
      await expect(row).toContainText(bomb.chain?'连锁提前引爆':'到期引爆');
    }
    if(id==='viewer-dead-owner')await expect(facts).toContainText('已淘汰，炸弹仍然有效');
    await pixels(frame); await screenshot(id);
    checks.push({id,explosions:frame.visual.exploded_bombs,coverage:frame.visual.coverage.length});
  }
  await open('reference-chain');
  for(const speed of ['0.25','0.5','1','2','4']) {
    await page.getByRole('button',{name:'初始帧 (Home)',exact:true}).click();
    await page.getByLabel('播放速度').selectOption(speed);
    await page.getByRole('button',{name:'播放 (Space)',exact:true}).click();
    await expect.poll(async()=>Number(await slider().inputValue()),{timeout:3000,intervals:[50]}).toBeGreaterThan(0);
    await page.getByRole('button',{name:'暂停 (Space)',exact:true}).click();
    const stopped=await slider().inputValue(); await page.waitForTimeout(180); await expect(slider()).toHaveValue(stopped);
  }
  await page.getByRole('button',{name:'初始帧 (Home)',exact:true}).click(); await slider().scrollIntoViewIfNeeded();
  const r=await slider().boundingBox();
  await page.mouse.move(r.x+8,r.y+r.height/2); await page.mouse.down();
  await page.mouse.move(r.x+r.width*.65,r.y+r.height/2,{steps:12}); await page.mouse.up();
  expect(Number(await slider().inputValue())).toBeGreaterThan(5);
  await page.getByRole('button',{name:'下一帧 (→)',exact:true}).click();
  const next=Number(await slider().inputValue()); await page.getByRole('button',{name:'上一帧 (←)',exact:true}).click();
  await expect(slider()).toHaveValue(String(next-1));
  await page.getByRole('button',{name:/爆炸.*炸弹 #/}).first().click(); await expect(slider()).toHaveValue('19');
  await page.getByRole('button',{name:'全屏 (F)',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>!!document.fullscreenElement)).toBe(true);
  await expect(page.getByRole('button',{name:'退出全屏 (F)',exact:true})).toBeVisible();
  await screenshot('viewer-fullscreen'); await page.getByRole('button',{name:'退出全屏 (F)',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>!!document.fullscreenElement)).toBe(false);
  checks.push({controls:{active_speeds:[.25,.5,1,2,4],pause:true,mouse_drag:true,steps:true,events:true,fullscreen:true}});
  await page.locator('h1').click(); await page.keyboard.press('Home'); await expect(slider()).toHaveValue('0');
  await page.keyboard.press('ArrowRight'); await expect(slider()).toHaveValue('1');
  await page.keyboard.press('f'); await expect.poll(()=>page.evaluate(()=>!!document.fullscreenElement)).toBe(true);
  await page.keyboard.press('Escape'); await expect.poll(()=>page.evaluate(()=>!!document.fullscreenElement)).toBe(false);
  await page.getByLabel('播放速度').focus(); await page.keyboard.press('ArrowLeft'); await expect(slider()).toHaveValue('1');
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.getByRole('button',{name:'初始帧 (Home)',exact:true}).click();
  await page.getByRole('button',{name:'播放 (Space)',exact:true}).click();
  await expect.poll(async()=>Number(await slider().inputValue())).toBeGreaterThan(1);
  await page.getByRole('button',{name:'暂停 (Space)',exact:true}).click();
  await page.emulateMedia({reducedMotion:'no-preference'});
  checks.push({keyboard:true,focused_input_not_hijacked:true,reduced_motion_playback:true});
  const entrants=(await (await context.request.get('/api/v1/entrants')).json()).items;
  const longMatch=(await (await context.request.get('/api/v1/matches?entrant=heuristic&tournament_id=reference-v01&limit=1')).json()).items[0].id;
  const original=(await (await context.request.get(`/api/v1/matches/${longMatch}`)).json());
  const swap=(await (await context.request.get(`/api/v1/matches/${original.swap_match_id}`)).json());
  expect(swap.entrants.map(e=>e.id)).toEqual(original.entrants.map(e=>e.id).reverse());
  await open(longMatch,1); await page.getByRole('link',{name:'同地图换边局',exact:true}).click();
  await expect(slider()).toHaveValue('1'); expect(new URL(page.url()).pathname).toBe(`/matches/${swap.id}`);
  await page.getByRole('link',{name:'同地图换边局',exact:true}).click();
  await expect(slider()).toHaveValue('1'); expect(new URL(page.url()).pathname).toBe(`/matches/${original.id}`);
  checks.push({swap_match:{original:original.id,swapped:swap.id,reverse_entrants:true,preserved_frame:1,roundtrip:true}});
  for(const width of [390,768,1280,1440]) {
    await page.setViewportSize({width,height:1000});
    for(const [name,path] of [['hall','/'],['viewer',`/matches/${longMatch}?frame=0`],['batch','/tournaments/reference-v01'],['entrants','/entrants'],['profile','/entrants/heuristic'],['manage','/manage']]) {
      await page.goto(path); await expect(page.locator('h1')).toBeVisible();
      if(name==='viewer')await expect(slider()).toHaveValue('0');
      if(name==='hall') {await expect(page.locator('.feature-match canvas')).toBeVisible(); await expect(page.locator('.match-row').first()).toBeVisible();}
      if(name==='batch') {await expect(page.locator('.ranking-row')).toHaveCount(3); await expect(page.locator('.case-dot')).toHaveCount(50); await expect(page.locator('.match-row')).toHaveCount(100);}
      if(name==='entrants')await expect(page.locator('.entrant-card')).toHaveCount(entrants.length);
      if(name==='profile')await expect(page.locator('.match-row')).toHaveCount(100);
      if(name==='manage')await expect(page.locator('[data-entrant-id="safe"]')).toBeVisible();
      await page.evaluate(()=>document.fonts.ready);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
      if(name==='viewer') {const box=await page.locator('canvas').boundingBox(); expect(Math.abs(box.width/box.height-13/11)).toBeLessThan(.001);}
      const contrast=await contrastReport(page); contrasts.push({page:name,width,...contrast});
      expect(contrast.failures,`${name}-${width} text contrast`).toEqual([]);
      if(contrast.field_boundary_ratio!==null)expect(contrast.field_boundary_ratio).toBeGreaterThanOrEqual(3);
      for(const terrain of contrast.terrain)expect(terrain.ratio).toBeGreaterThanOrEqual(3);
      await screenshot(`${name}-${width}`);
      if(width===390||name==='batch'&&width===1440) {
        const preview=`${name}-${width}-viewport.png`;
        await page.screenshot({path:resolve(visual,preview),fullPage:false}); snapshots.push(preview);
      }
    }
  }
  await page.goto('/tournaments/reference-v01?pair=heuristic,bomber&case=0');
  await expect(page.locator('.case-dot.selected')).toHaveCount(1);
  const selectedContrast=await contrastReport(page); contrasts.push({page:'selected-case',...selectedContrast}); expect(selectedContrast.failures).toEqual([]);
  await page.goto('/matches/reference-chain'); await expect(slider()).toHaveValue('0');
  await page.keyboard.press('Tab');
  await expect(page.locator('.skip-link')).toBeFocused();
  const focus=await page.locator('.skip-link').evaluate(el=>({style:getComputedStyle(el).outlineStyle,width:parseFloat(getComputedStyle(el).outlineWidth),visible:el.getBoundingClientRect().top>=0}));
  expect(focus.visible).toBe(true); expect(focus.style).toBe('solid'); expect(focus.width).toBeGreaterThanOrEqual(2);
  await page.keyboard.press('Enter'); await expect(page.locator('main')).toBeFocused();
  const touch=await browser.newContext({baseURL:base,viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  try {
    const mobile=await touch.newPage(); mobile.on('pageerror',e=>errors.push(e.message));
    await mobile.goto('/matches/reference-chain'); const range=mobile.getByRole('slider',{name:'回放帧'});
    await expect(range).toHaveValue('0');
    const board=await mobile.locator('canvas').boundingBox();
    await mobile.touchscreen.tap(board.x+board.width*5.5/13,board.y+board.height*5.5/11);
    await expect(mobile.getByLabel('格子 x')).toHaveValue('5'); await expect(mobile.getByLabel('格子 y')).toHaveValue('5');
    await range.scrollIntoViewIfNeeded(); const r=await range.boundingBox(), cdp=await touch.newCDPSession(mobile);
    const y=r.y+r.height/2;
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:r.x+8,y}]});
    for(let step=1;step<=12;step++)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:r.x+8+(r.width*.75-8)*step/12,y}]});
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    expect(Number(await range.inputValue())).toBeGreaterThan(5);
    for(const name of ['上一帧 (←)','播放 (Space)','下一帧 (→)']) {const box=await mobile.getByRole('button',{name,exact:true}).boundingBox(); expect(box.width).toBeGreaterThanOrEqual(44); expect(box.height).toBeGreaterThanOrEqual(44);}
    await mobile.screenshot({path:resolve(visual,'viewer-native-touch.png'),fullPage:true}); snapshots.push('viewer-native-touch.png');
    checks.push({native_touch:{board_selection:[5,5],range_drag:true,transport_minimum:44},keyboard_skip_link:focus});
  } finally {await touch.close();}
  expect(errors).toEqual([]);
  const video=await page.video().path();
  await context.close();
  writeFileSync(resolve(output,'checks/viewer-quality.json'),JSON.stringify({status:'passed',browser:await browser.version(),checks,screenshots:snapshots,video:video.split(/[\\/]/).at(-1),contrasts,page_errors:errors},null,2));
  console.log(`Verified ${checks.length} viewer groups and ${snapshots.length} rendered screenshots.`);
} finally { await context?.close(); await browser.close(); }
