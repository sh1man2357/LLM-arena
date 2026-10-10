/** Verify native spectator operations during confirmed real compile and match jobs. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {chromium,expect} from '@playwright/test';
import {instrumentation,summary,animationStats} from './performance-instrumentation.mjs';

const [base='http://127.0.0.1:8801',outArg='../artifacts/work/checks',run='initial']=process.argv.slice(2);
const out=resolve(outArg),checks=resolve(out,'checks'),visual=resolve(out,'visual/performance');mkdirSync(visual,{recursive:true});
const fixture=JSON.parse(readFileSync(resolve(checks,'performance-fixture.json'),'utf8'));
const browser=await chromium.launch({channel:'chrome'}),context=await browser.newContext({baseURL:base,viewport:{width:1280,height:1000}});
await context.addInitScript(instrumentation);
const page=await context.newPage(),errors=[],work=[];page.on('pageerror',e=>errors.push(e.message));
let result={status:'incomplete',browser:await browser.version(),fixture,work,page_errors:errors};
const api=context.request;
async function getJob(id){const r=await api.get(`/api/v1/jobs/${id}`);expect(r.ok()).toBe(true);return r.json();}
async function post(path,data,key){const r=await api.post(path,{data,headers:{origin:base,...(key?{'idempotency-key':key}:{})}});expect(r.ok(),await r.text()).toBe(true);return r.json();}
async function nativeSeek(key){
  const slider=page.getByRole('slider',{name:'回放帧'});await slider.focus();
  const count=await page.evaluate(()=>window.__spectatorPerf.seeks.length);await page.keyboard.press(key);
  await expect.poll(()=>page.evaluate(()=>window.__spectatorPerf.seeks.length)).toBe(count+1);
  const value=await page.evaluate(()=>window.__spectatorPerf.seeks.at(-1));
  expect(value.frame_at_paint).toBe(value.frame);
  expect(value.label).toContain(value.frame===0?'初始状态':`Tick ${value.frame-1} 已结算`);
  return {...value,latency_ms:value.paint-value.input};
}
async function observe(job,kind){
  const samples=[];
  const record={kind,job_id:job.id,resources:job.resources,samples};work.push(record);
  await expect.poll(async()=> (await getJob(job.id)).status,{timeout:15000}).toBe('running');
  const beforePlay=await getJob(job.id);
  await page.getByRole('button',{name:'初始帧 (Home)',exact:true}).click();
  await page.getByRole('button',{name:'播放 (Space)',exact:true}).click();
  const playStart=await page.evaluate(()=>{window.__spectatorPerf.draws=[];return performance.now();});
  await expect.poll(async()=>Number(await page.getByRole('slider',{name:'回放帧'}).inputValue()),{timeout:8000,intervals:[50]}).toBeGreaterThanOrEqual(4);
  const playStats=await page.evaluate(()=>({at:performance.now(),draws:window.__spectatorPerf.draws}));
  await page.getByRole('button',{name:'暂停 (Space)',exact:true}).click();
  const afterPlay=await getJob(job.id);
  const playback={before_status:beforePlay.status,after_status:afterPlay.status,...animationStats(playStats.draws,playStats.at-playStart)};
  record.playback=playback;
  for(let n=0;n<12;n++) {
    const before=await getJob(job.id);if(before.status!=='running')break;
    const seek=await nativeSeek(n%2===0?'End':'Home');
    const started=performance.now(),health=await api.get('/health'),frames=await api.get(`/api/v1/matches/${fixture.match_id}/frames`);
    expect(health.ok()).toBe(true);expect(frames.ok()).toBe(true);expect((await frames.json()).frames).toHaveLength(501);
    const api_ms=performance.now()-started,after=await getJob(job.id);
    samples.push({before:{status:before.status,attempt_id:before.attempt_id,progress:before.progress},after:{status:after.status,attempt_id:after.attempt_id,progress:after.progress},seek,api_ms});
    if(after.status!=='running')break;
  }
  const bracketed=samples.filter(s=>s.before.status==='running'&&s.after.status==='running');
  Object.assign(record,{bracketed_samples:bracketed.length,
    seek_ms:summary(bracketed.map(s=>s.seek.latency_ms)),api_ms:summary(bracketed.map(s=>s.api_ms))});
  expect(bracketed.length,`${kind}: confirmed running before and after operation`).toBeGreaterThanOrEqual(3);
  expect(playback.before_status).toBe('running');expect(playback.after_status).toBe('running');
  await page.screenshot({path:resolve(visual,`${kind}-${run}.png`)});
  await expect.poll(async()=> (await getJob(job.id)).status,{timeout:60000,intervals:[100,250,500]}).toBe('succeeded');
  record.final_job=await getJob(job.id);
  return record;
}
try {
  const unlocked=await api.post('/api/v1/admin/unlock',{headers:{'x-arena-local':'1'}});expect(unlocked.ok()).toBe(true);
  await page.goto(`/matches/${fixture.match_id}`);await expect(page.locator('.spectator-stage')).toHaveAttribute('data-frame-count','501');
  // Genuine C++ source with standard library parsing work; no sleeping compiler wrapper.
  const source=['#include "arena.hpp"',...['vector','queue','unordered_map','map','set','algorithm','numeric','random','functional','memory','string','bitset','complex','valarray','regex'].map(h=>`#include <${h}>`),
    'namespace bot { void init(uint64_t) {} Action tick(const GameState&) { return Action::WAIT; } }',''].join('\n');
  const session=await post('/api/v1/sessions',{name:`性能 Wait ${run} ${Date.now()}`,model:'工程性能检查，非模型生成'});
  const submission=await post(`/api/v1/sessions/${session.id}/submit`,{source});
  const compile=await post(`/api/v1/submissions/${submission.id}/compile`,{},`perf-compile-${submission.id}`);
  const repeated=await post(`/api/v1/submissions/${submission.id}/compile`,{},`perf-compile-${submission.id}`);expect(repeated.id).toBe(compile.id);
  const compilation=await observe(compile,'compile');
  const submitted=await(await api.get(`/api/v1/submissions/${submission.id}`)).json();expect(submitted.status).toBe('qualified');
  compilation.submission={id:submitted.id,source_sha256:submitted.source_sha256,wasm_sha256:submitted.wasm_sha256,status:submitted.status};
  const match=await post('/api/v1/matches',{entrant_ids:[submitted.entrant_id,'safe'],map_seed:1,title:`性能验收 ${run} WAIT / Safe`,tick_interval_ms:50},`perf-match-${submission.id}`);
  const repeatMatch=await post('/api/v1/matches',{entrant_ids:[submitted.entrant_id,'safe'],map_seed:1,title:`性能验收 ${run} WAIT / Safe`,tick_interval_ms:50},`perf-match-${submission.id}`);expect(repeatMatch.id).toBe(match.id);
  const matching=await observe(match,'match');
  const final=await(await api.get(`/api/v1/matches/${match.resources.match_id}`)).json();expect(final.ticks).toBe(500);expect(final.verified).toBe(true);expect(final.result.valid).toBe(true);
  matching.match={id:final.id,ticks:final.ticks,source_sha256:final.source_sha256,verified:final.verified};
  expect(matching.playback.before_status).toBe('running');expect(matching.playback.after_status).toBe('running');
  expect(work.flatMap(w=>w.playback.player0_interpolation_reversals),'background updates do not rewind moves').toEqual([]);
  expect(work.flatMap(w=>w.samples.filter(s=>s.before.status==='running'&&s.after.status==='running').map(s=>s.seek.latency_ms)).every(ms=>ms<=100)).toBe(true);
  expect(errors).toEqual([]);result.status='measured';
} catch(error) {result.error=error.message;throw error;} finally {
  writeFileSync(resolve(checks,`performance-background-${run}.json`),JSON.stringify(result,null,2)+'\n');
  await context.close();await browser.close();
}
console.log(`Measured real compile/match background operations: ${work.map(w=>`${w.kind} ${w.bracketed_samples}`).join(', ')}`);
