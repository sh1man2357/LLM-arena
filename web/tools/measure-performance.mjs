/** Measure production spectator paint and native input; no mocked HTTP or animation. */
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {chromium, expect} from '@playwright/test';
import {instrumentation, summary, animationStats} from './performance-instrumentation.mjs';

const [base='http://127.0.0.1:8801', outArg='../artifacts/acceptance/v0.2-development', run='initial']=process.argv.slice(2);
const out=resolve(outArg), checks=resolve(out,'checks');mkdirSync(checks,{recursive:true});
const fixture=JSON.parse(readFileSync(resolve(checks,'performance-fixture.json'),'utf8'));
const machine=JSON.parse(readFileSync(resolve(checks,'performance-machine.json'),'utf8'));
const browser=await chromium.launch({channel:'chrome'}), errors=[], navigations=[], seeks=[], animations=[];
const file=resolve(checks,`performance-${run}.json`);
let context,page,passed=false;
try {
  if(run==='boundary') {
    const uploadContext=await browser.newContext({baseURL:base});
    try {
      const unlock=await uploadContext.request.post('/api/v1/admin/unlock',{headers:{'x-arena-local':'1'}});expect(unlock.ok()).toBe(true);
      const start=performance.now();
      const imported=await uploadContext.request.post('/api/v1/imports/replay',{headers:{origin:base},multipart:{file:{name:'boundary-replay.jsonl',mimeType:'application/x-ndjson',buffer:readFileSync(resolve('..',fixture.size_boundary.file))}}});
      expect(imported.ok(),await imported.text()).toBe(true);
      const row=await imported.json();expect(row.verified).toBe(true);expect(row.ticks).toBe(500);
      expect(row.source_sha256).toBe(fixture.size_boundary.source_sha256);
      fixture.original_match_id=fixture.match_id;fixture.match_id=row.id;
      fixture.replay_bytes=fixture.size_boundary.replay_bytes;fixture.source_sha256=fixture.size_boundary.source_sha256;
      fixture.import_ms=performance.now()-start;
    }finally{await uploadContext.close();}
  }
  for(const width of [390,768,1280,1440])for(let repetition=0;repetition<3;repetition++) {
    // Every navigation gets a new context, empty HTTP cache and no prior loaded Replay.
    context=await browser.newContext({baseURL:base,viewport:{width,height:1000},reducedMotion:'no-preference'});
    await context.addInitScript(instrumentation);page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    const response=await page.goto(`/matches/${fixture.match_id}`);expect(response.ok()).toBe(true);
    await expect(page.locator('.spectator-stage')).toHaveAttribute('data-frame-count','501');
    await expect.poll(()=>page.evaluate(()=>window.__spectatorPerf.firstPaint)).toBeGreaterThan(0);
    const measurement=await page.evaluate(()=>({first_paint_ms:window.__spectatorPerf.firstPaint,
      frame:Number(document.querySelector('input[aria-label="回放帧"]').value),
      resources:performance.getEntriesByType('resource').filter(e=>e.name.includes('/frames')).map(e=>({name:new URL(e.name).pathname,duration_ms:e.duration,transfer_bytes:e.transferSize,decoded_bytes:e.decodedBodySize})),
      visibility:document.visibilityState,dpr:devicePixelRatio}));
    expect(measurement.frame).toBe(0);navigations.push({width,repetition,...measurement});
    console.log(`Navigation ${width}/${repetition}: ${measurement.first_paint_ms.toFixed(1)} ms`);
    const slider=page.getByRole('slider',{name:'回放帧'});await slider.focus();
    for(const key of ['End','Home','PageUp','PageUp','PageDown','End','PageDown','PageDown','Home','ArrowRight','ArrowRight','End']) {
      const count=await page.evaluate(()=>window.__spectatorPerf.seeks.length);
      await page.keyboard.press(key);
      await expect.poll(()=>page.evaluate(()=>window.__spectatorPerf.seeks.length)).toBe(count+1);
      const sample=await page.evaluate(()=>window.__spectatorPerf.seeks.at(-1));
      expect(sample.frame_at_paint).toBe(sample.frame);
      expect(sample.label).toContain(sample.frame===0?'初始状态':`Tick ${sample.frame-1} 已结算`);
      seeks.push({width,repetition,key,...sample,latency_ms:sample.paint-sample.input});
    }
    if(repetition===0) {
      await page.getByRole('button',{name:'初始帧 (Home)',exact:true}).click();
      await page.getByRole('button',{name:'播放 (Space)',exact:true}).click();
      const start=await page.evaluate(()=>{window.__spectatorPerf.draws=[];return performance.now();});
      // Wait for actual playback progress rather than a synthetic RAF counter.
      await expect.poll(async()=>Number(await slider.inputValue()),{timeout:12000}).toBeGreaterThanOrEqual(32);
      const stats=await page.evaluate(()=>({elapsed:performance.now(),draws:window.__spectatorPerf.draws}));
      await page.getByRole('button',{name:'暂停 (Space)',exact:true}).click();
      animations.push({width,...animationStats(stats.draws,stats.elapsed-start)});
    }
    await context.close();context=null;
  }
  expect(errors).toEqual([]);
  expect(navigations.every(n=>n.first_paint_ms<=1500),'all first paints ≤1.5s').toBe(true);
  expect(seeks.every(s=>s.latency_ms<=100),'all native seeks ≤100ms').toBe(true);
  expect(animations.every(a=>a.canvas_animation_fps>=55),'actual Canvas animation draws over full wall interval ≥55 FPS').toBe(true);
  expect(animations.flatMap(a=>a.player0_interpolation_reversals),'movement never rewinds within a confirmed Tick').toEqual([]);
  passed=true;
} finally {
  if(context)await context.close();
  writeFileSync(file,JSON.stringify({kind:'production_spectator_performance',status:passed?'passed':'incomplete_or_threshold_failed',
    browser:await browser.version(),machine,fixture,method:{first_paint:'navigation time origin to two RAF callbacks after first real Canvas draw; conservative presentation bound',seek:'native range keyboard input to two RAF callbacks after matching real Canvas draw',http_cache:'new browser context for every run; local server and OS files may be warm',viewport_height:1000},
    thresholds:{first_paint_ms:1500,loaded_seek_ms:100,normal_canvas_fps:55},
    navigations,seeks,animations,summary:{first_paint_ms:summary(navigations.map(n=>n.first_paint_ms)),seek_ms:summary(seeks.map(s=>s.latency_ms))},page_errors:errors},null,2)+'\n');
  await browser.close();
}
console.log(`Saved ${file}`);
