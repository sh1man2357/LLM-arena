import { test, expect, type Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const output = process.env.ARENA_RECEIPT_EVIDENCE;
const source = '#include "arena.hpp"\n// UTF-8 单文件提交\nnamespace bot { void init(uint64_t) {} Action tick(const GameState&) { return Action::WAIT; } }\n';
const sha = (value: string) => createHash('sha256').update(value).digest('hex');
async function views(page: Page, name: string) {
  for (const width of [390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    if (output) { mkdirSync(resolve(output), {recursive: true}); await page.screenshot({path: resolve(output, `${name}-${width}.png`), fullPage: true}); }
  }
}
async function post(page: Page, path: string, data: unknown = undefined) {
  const response = await page.request.post(path, {data, headers: {'Idempotency-Key': crypto.randomUUID()}});
  expect(response.ok(), await response.text()).toBeTruthy(); return response.json();
}

test('uploaded source freezes early, compiles and has an owner-only traceable receipt', async ({page, browser}) => {
  test.setTimeout(60000);
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  const name = `上传工程 ${Date.now()} ${'长名称'.repeat(25)}`;
  await page.goto('/manage');
  await page.getByLabel('参赛者名称', {exact:true}).fill(name);
  await page.getByLabel('模型标识', {exact:true}).fill('工程验证，非模型生成');
  const created = page.waitForResponse(r => r.url().endsWith('/api/v1/sessions') && r.request().method() === 'POST');
  await page.getByRole('button', {name:'记录收到任务，开始 60 分钟', exact:true}).click();
  const session = await (await created).json();
  expect(Date.parse(session.deadline) - Date.parse(session.started_at)).toBe(3600000);
  await expect(page.getByLabel('选择收卷记录')).toHaveValue(session.id);
  await page.getByRole('link', {name:'收卷档案', exact:true}).click();
  await expect(page.locator('.badge').filter({hasText:'开发中'})).toBeVisible();
  await views(page, 'open');
  await page.getByRole('link', {name:'继续收卷', exact:true}).click();
  await expect(page.getByLabel('选择收卷记录')).toHaveValue(session.id);
  await page.getByLabel('载入 bot.cpp', {exact:true}).setInputFiles({name:'bot.cpp', mimeType:'text/plain', buffer:Buffer.from(source)});
  await expect(page.getByLabel('最终 bot.cpp', {exact:true})).toHaveValue(source);
  const submitted = page.waitForResponse(r => r.url().endsWith('/submit') && r.request().method() === 'POST');
  await page.getByRole('button', {name:'最终交卷并冻结', exact:true}).click();
  const submission = await (await submitted).json();
  expect(submission.source_sha256).toBe(sha(source)); expect(submission.late).toBe(false);
  expect(Date.parse(submission.received_at)).toBeLessThan(Date.parse(session.deadline));
  await expect(page.getByLabel('最终 bot.cpp')).toHaveCount(0);
  const duplicate = await post(page, `/api/v1/sessions/${session.id}/submit`, {source});
  expect(duplicate.id).toBe(submission.id);
  expect((await page.request.post(`/api/v1/sessions/${session.id}/submit`, {data:{source:source+'// replacement'}})).status()).toBe(409);
  await page.getByRole('link', {name:'收卷档案', exact:true}).click();
  await expect(page.locator('dl')).toContainText(submission.source_sha256);
  await views(page, 'submitted');
  await page.getByRole('link', {name:'在工作台查看与管理', exact:true}).click();
  const row = page.locator('.submission-row').filter({hasText:name});
  await row.getByRole('button', {name:'编译并检查资格', exact:true}).click();
  await expect(row.getByText('资格通过', {exact:true})).toBeVisible({timeout:20000});
  await page.getByRole('link', {name:'收卷档案', exact:true}).click();
  await expect(page.getByRole('link', {name:'查看可参赛程序', exact:true})).toBeVisible();
  const receipt = await (await page.request.get(`/api/v1/receipts/${session.id}`)).json();
  expect(receipt.status).toBe('qualified'); expect(receipt.submission.source_sha256).toBe(sha(source));
  expect(receipt.submission.wasm_sha256).toMatch(/^[0-9a-f]{64}$/); expect(receipt.submission.qualification).toBeTruthy();
  expect(receipt.job.status).toBe('succeeded');
  expect(await (await page.request.get(`/api/v1/submissions/${submission.id}/source`)).text()).toBe(source);
  await views(page, 'qualified');
  const guest = await browser.newContext({baseURL: test.info().project.use.baseURL});
  try {
    const spectator = await guest.newPage();
    expect(await (await guest.request.get('/api/v1/admin/status')).json()).toEqual({owner:false});
    for (const path of [`/api/v1/receipts/${session.id}`, '/api/v1/receipts/unknown', `/api/v1/submissions/${submission.id}/source`]) expect((await guest.request.get(path)).status()).toBe(403);
    await spectator.goto(`/entrants/receipts/${session.id}`);
    await expect(spectator.getByRole('heading', {name:'收卷档案仅供主办方查看', exact:true})).toBeVisible();
    await expect(spectator.locator('main')).not.toContainText(name);
    await views(spectator, 'private');
  } finally {await guest.close();}
  await page.goto('/entrants');
  await expect(page.locator(`[data-receipt-id="${session.id}"]`)).toBeVisible();
  await page.goto('/entrants/receipts/unknown');
  await expect(page.getByRole('heading', {name:'没有找到这份资料', exact:true})).toBeVisible();
  expect(errors).toEqual([]);
  if (output) writeFileSync(resolve(output, 'qualified-api.json'), JSON.stringify({session,receipt},null,2)+'\n');
});

test('missing, late and compiler failure records remain browsable and never enter the program pool', async ({page}) => {
  test.setTimeout(60000);
  await page.goto('/manage'); await expect(page.getByLabel('参赛者名称', {exact:true})).toBeEnabled();
  const initial = (await (await page.request.get('/api/v1/entrants')).json()).items.map((r:any)=>r.id);
  const name = `失败 <script>工程</script> ${Date.now()}`;
  const failed = await post(page,'/api/v1/sessions',{name, model:'工程诊断'});
  const invalid = 'this is invalid C++ <script>error</script>';
  const submission = await post(page,`/api/v1/sessions/${failed.id}/submit`,{source:invalid});
  await post(page,`/api/v1/submissions/${submission.id}/compile`);
  await page.goto(`/entrants/receipts/${failed.id}`);
  await expect(page.locator('[data-receipt-diagnostic]')).toContainText('error:',{timeout:20000});
  await expect(page.getByRole('heading', {name,exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'查看可参赛程序',exact:true})).toHaveCount(0);
  await views(page,'qualification-failed');
  const expired = await post(page,'/api/v1/sessions',{name:`未交卷 ${Date.now()}`,model:'工程时间记录',time_source:'external_record',started_at:new Date(Date.now()-4200000).toISOString()});
  await page.goto(`/entrants/receipts/${expired.id}`);
  await expect(page.locator('.notice[role="status"]').first()).toContainText('截止时间已到');
  await views(page,'missing');
  const late = await post(page,`/api/v1/sessions/${expired.id}/submit`,{source});
  expect(late.late).toBe(true);
  expect((await page.request.post(`/api/v1/submissions/${late.id}/compile`)).status()).toBe(409);
  await expect(page.locator('.notice[role="status"]').first()).toContainText('晚于固定截止时间');
  await views(page,'late');
  const ticking = await post(page,'/api/v1/sessions',{name:`实际到期 ${Date.now()}`,model:'工程时间记录',time_source:'external_record',started_at:new Date(Date.now()-3600000+9000).toISOString()});
  expect(Date.parse(ticking.deadline)-Date.parse(ticking.started_at)).toBe(3600000);
  await page.goto(`/entrants/receipts/${ticking.id}`);
  await expect(page.locator('.notice[role="status"]').first()).toContainText('仍在开发时限内');
  await expect(page.locator('.notice[role="status"]').first()).toContainText('截止时间已到',{timeout:16000});
  await page.goto(`/manage?session=${ticking.id}`);
  await expect(page.getByLabel('选择收卷记录')).toHaveValue(ticking.id);
  await page.getByLabel('最终 bot.cpp').fill('draft of first receipt');
  await page.getByLabel('选择收卷记录').selectOption(failed.id);
  await expect(page.getByLabel('最终 bot.cpp')).toHaveCount(0);
  await page.getByLabel('选择收卷记录').selectOption(ticking.id);
  await expect(page.getByLabel('最终 bot.cpp')).toHaveValue('');
  expect((await (await page.request.get('/api/v1/entrants')).json()).items.map((r:any)=>r.id)).toEqual(initial);
  await page.goto('/entrants');
  for (const id of [failed.id,expired.id,ticking.id]) await expect(page.locator(`[data-receipt-id="${id}"]`)).toBeVisible();
  if (output) writeFileSync(resolve(output,'failed-and-time-api.json'),JSON.stringify({records:await (await page.request.get('/api/v1/receipts')).json(), deadline_method:'Actual server deadline; external start records are engineering samples, interval remains 3600 seconds.'},null,2)+'\n');
});

test('unfinished batch preserves single-match facts and cannot show or publish formal rankings', async ({page}) => {
  test.setTimeout(60000);
  await page.goto('/manage');
  await expect(page.getByRole('button',{name:'创建全配对批次',exact:true})).toBeVisible();
  const entrants = (await (await page.request.get('/api/v1/entrants')).json()).items;
  const wait = entrants.find((r:any)=>r.name.startsWith('上传工程') && r.status === 'qualified');
  expect(wait).toBeTruthy();
  await page.locator(`[data-entrant-id="${wait.id}"]`).getByRole('checkbox').check();
  await page.locator('[data-entrant-id="safe"]').getByRole('checkbox').check();
  const title = `边界停止工程 ${Date.now()}`;
  await page.getByLabel('比赛标题',{exact:true}).fill(title);
  await page.getByLabel('批次地图数',{exact:true}).fill('50');
  const created = page.waitForResponse(r=>r.url().endsWith('/api/v1/tournaments') && r.request().method()==='POST');
  await page.getByRole('button',{name:'创建全配对批次',exact:true}).click();
  const job = await (await created).json();
  await expect.poll(async()=> (await (await page.request.get(`/api/v1/jobs/${job.id}`)).json()).progress,{timeout:20000}).toBeGreaterThan(0);
  await page.locator(`[data-job-id="${job.id}"]`).getByRole('button',{name:'当前局后停止',exact:true}).click();
  await expect.poll(async()=> (await (await page.request.get(`/api/v1/jobs/${job.id}`)).json()).status,{timeout:20000}).toBe('stopped');
  const batchId = job.resources.tournament_id;
  const batch = await (await page.request.get(`/api/v1/tournaments/${batchId}`)).json();
  expect(batch.completed_matches).toBeGreaterThan(0); expect(batch.completed_matches).toBeLessThan(batch.expected_matches);
  expect(batch.report.status).toBe('incomplete');
  expect((await page.request.post(`/api/v1/tournaments/${batchId}/publish`)).status()).toBe(409);
  const publication = page.locator('.publication-row').filter({hasText:title});
  await expect(publication.getByRole('button',{name:'校验并发布成绩',exact:true})).toHaveCount(0);
  await page.goto(`/tournaments/${batchId}`);
  await expect(page.getByText('当前批次尚未完成。这里只显示进度和单局事实，不发布正式汇总排名。',{exact:true})).toBeVisible();
  await expect(page.locator('.ranking-row')).toHaveCount(0);
  await expect(page.locator('.match-row').first()).toBeVisible();
  await views(page,'incomplete-batch');
  if (output) writeFileSync(resolve(output,'incomplete-batch-api.json'),JSON.stringify({job:await (await page.request.get(`/api/v1/jobs/${job.id}`)).json(),batch,publication_response:409},null,2)+'\n');
});
