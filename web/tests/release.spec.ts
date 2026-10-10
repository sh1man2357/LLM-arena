import {test,expect} from '@playwright/test';
import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';

const out=process.env.ARENA_FINAL_EVIDENCE;
test('UI freezes an actual hidden schedule, guards every spectator read and publishes only after close',async({page,browser})=>{
  test.setTimeout(60000);
  await page.goto('/manage');
  for(const id of ['safe','heuristic'])await page.locator(`[data-entrant-id="${id}"]`).getByRole('checkbox').check();
  const title=`正式封存工程 ${Date.now()}`;
  await page.getByLabel('比赛标题',{exact:true}).fill(title);await page.getByLabel('批次地图数',{exact:true}).fill('1');
  await page.getByRole('checkbox',{name:'正式隐藏批次，收卷关闭前封存地图',exact:true}).check();
  const created=page.waitForResponse(r=>r.url().endsWith('/api/v1/tournaments')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'创建全配对批次',exact:true}).click();const job=await(await created).json();const id=job.resources.tournament_id;
  await expect.poll(async()=> (await(await page.request.get(`/api/v1/jobs/${job.id}`)).json()).status,{timeout:25000}).toBe('succeeded');
  const matches=(await(await page.request.get(`/api/v1/matches?tournament_id=${id}`)).json()).items;expect(matches).toHaveLength(2);
  const guest=await browser.newContext({baseURL:test.info().project.use.baseURL});
  const checks=[];
  try{
    const reads=[`/api/v1/tournaments/${id}`,`/api/v1/tournaments/${id}/report`,`/api/v1/tournaments/${id}/analysis`,`/api/v1/exports/${id}?kind=report`,`/api/v1/exports/${id}?kind=publication`];
    for(const m of matches)reads.push(`/api/v1/matches/${m.id}`,`/api/v1/matches/${m.id}/frames`,`/api/v1/exports/${m.id}`);
    for(const path of reads){const response=await guest.request.get(path);expect(response.status()).toBe(403);checks.push({path,before:403});}
    expect((await(await guest.request.get('/api/v1/tournaments')).json()).items.find((r:any)=>r.id===id)).toBeFalsy();
    expect((await(await guest.request.get(`/api/v1/matches?tournament_id=${id}`)).json()).total).toBe(0);
    const spectator=await guest.newPage();await spectator.goto(`/tournaments/${id}`);await expect(spectator.getByRole('heading',{name:'当前资料暂未开放',exact:true})).toBeVisible();
    expect((await page.request.post(`/api/v1/tournaments/${id}/publish`)).status()).toBe(409);
    const row=page.locator('.publication-row').filter({hasText:title});await row.getByRole('button',{name:'关闭收卷并开放观看',exact:true}).click();
    await row.getByRole('button',{name:'校验并发布成绩',exact:true}).click();await expect(row.getByRole('link',{name:'下载发布清单',exact:true})).toBeVisible();
    const closed=await(await page.request.get(`/api/v1/tournaments/${id}`)).json();expect(closed.window_close_source).toBe('host_confirmation');expect(closed.window_closed_entrants).toHaveLength(2);
    for(const item of checks){const response=await guest.request.get(item.path);expect(response.ok()).toBeTruthy();const text=await response.text();for(const marker of ['"map_seed"','"bot_seeds"','"source_files"','C:\\Users','"diagnostic"','"wasm":'])expect(text).not.toContain(marker);Object.assign(item,{after:200,sha256:createHash('sha256').update(await response.body()).digest('hex')});}
    await spectator.reload();await expect(spectator.locator('.ranking-row')).toHaveCount(2);
    if(out){mkdirSync(resolve(out,'checks'),{recursive:true});writeFileSync(resolve(out,'checks/runtime-api.json'),JSON.stringify({job,closed,matches,reads:checks},null,2)+'\n');}
  }finally{await guest.close();}
});

test('corrupt and unknown Replay uploads explain failure without registering a match or losing the source draft',async({page})=>{
  await page.goto('/manage');
  await page.getByLabel('参赛者名称',{exact:true}).fill('异常状态检查');
  await expect(page.getByRole('button',{name:'记录收到任务，开始 60 分钟',exact:true})).toBeEnabled();
  const created=await page.request.post('/api/v1/sessions',{data:{name:`异常状态工程 ${Date.now()}`}});expect(created.ok()).toBeTruthy();const session=await created.json();
  await page.getByLabel('选择收卷记录').selectOption(session.id);await page.getByLabel('最终 bot.cpp').fill('preserved source draft');
  const before=(await(await page.request.get('/api/v1/matches?limit=1')).json()).total;
  const replay=readFileSync(resolve('../artifacts/work/browser-fixtures/chain.jsonl'),'utf8');
  const unknown=replay.replace(/"schema_version"\s*:\s*1/,'"schema_version":99');expect(unknown).not.toBe(replay);
  for(const [name,data,reason]of [['unknown.jsonl',unknown,'schema'],['corrupt.jsonl','{broken','Expecting property']]){
    const response=page.waitForResponse(r=>r.url().endsWith('/api/v1/imports/replay')&&r.request().method()==='POST');
    await page.getByLabel('上传 Replay',{exact:true}).setInputFiles({name,mimeType:'application/x-ndjson',buffer:Buffer.from(data)});
    expect((await response).status()).toBe(422);
    await expect(page.locator('.workflow-message')).toContainText(reason);await expect(page.getByLabel('最终 bot.cpp')).toHaveValue('preserved source draft');
    expect((await(await page.request.get('/api/v1/matches?limit=1')).json()).total).toBe(before);
  }
});

test('actual FIFO compile queue can stop and resume a frozen receipt while a real match keeps running',async({page})=>{
  test.setTimeout(60000);
  await page.goto('/manage');await page.getByLabel('参赛者名称',{exact:true}).fill('队列检查');
  await expect(page.getByRole('button',{name:'记录收到任务，开始 60 分钟',exact:true})).toBeEnabled();
  const entrants=(await(await page.request.get('/api/v1/entrants')).json()).items;
  const wait=entrants.find((e:any)=>e.name.startsWith('上传工程')&&e.status==='qualified');expect(wait).toBeTruthy();
  const running=await(await page.request.post('/api/v1/matches',{data:{entrant_ids:['safe',wait.id],map_seed:1,title:'真实排队窗口工程',tick_interval_ms:50}})).json();
  await expect.poll(async()=> (await(await page.request.get(`/api/v1/jobs/${running.id}`)).json()).status).toBe('running');
  const session=await(await page.request.post('/api/v1/sessions',{data:{name:`编译排队工程 ${Date.now()}`}})).json();
  const source='#include "arena.hpp"\nnamespace bot {void init(uint64_t){} Action tick(const GameState&){return Action::WAIT;}}';
  const frozen=await(await page.request.post(`/api/v1/sessions/${session.id}/submit`,{data:{source}})).json();
  const compile=await(await page.request.post(`/api/v1/submissions/${frozen.id}/compile`)).json();
  await page.goto(`/entrants/receipts/${session.id}`);await expect(page.getByText('编译作业已排队，冻结源码不会重新开放修改。',{exact:true})).toBeVisible();
  if(out)await page.screenshot({path:resolve(out,'visual/queued-receipt-1280.png'),fullPage:true});
  await page.getByRole('link',{name:'在工作台查看与管理',exact:true}).click();
  const row=page.locator(`[data-job-id="${compile.id}"]`);await row.getByRole('button',{name:'停止排队',exact:true}).click();
  await expect(row.getByRole('button',{name:'恢复 / 重试',exact:true})).toBeVisible();
  await row.getByRole('button',{name:'恢复 / 重试',exact:true}).click();
  await page.goto(`/entrants/receipts/${session.id}`);
  await expect(page.getByText('正在统一编译与资格检查，请等待实际执行结果。',{exact:true})).toBeVisible({timeout:40000});
  if(out)await page.screenshot({path:resolve(out,'visual/compiling-receipt-1280.png'),fullPage:true});
  await expect.poll(async()=> (await(await page.request.get(`/api/v1/jobs/${running.id}`)).json()).status,{timeout:40000}).toBe('succeeded');
  await expect.poll(async()=> (await(await page.request.get(`/api/v1/jobs/${compile.id}`)).json()).status,{timeout:25000}).toBe('succeeded');
  const receipt=await(await page.request.get(`/api/v1/receipts/${session.id}`)).json();expect(receipt.submission.source_sha256).toBe(frozen.source_sha256);expect(receipt.status).toBe('qualified');
  if(out)writeFileSync(resolve(out,'checks/queued-receipt-api.json'),JSON.stringify({receipt,real_match:running,source_unchanged:true},null,2)+'\n');
});
