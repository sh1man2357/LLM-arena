import { test, expect } from '@playwright/test';

const source = Buffer.from('#include "gomoku.hpp"\nnamespace bot { void init(uint64_t){} Action tick(const GameState& s){return {int(s.move_count/2),s.self_color==1?0:14};} }');

test('五子棋导入、换色、开局、回放、榜单与窄屏', async ({page, request}, testInfo) => {
  const errors: string[] = []; page.on('pageerror', e => errors.push(e.message));
  await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s => s.busy), {timeout: 40000}).toBe(false);
  await page.goto('/'); await page.getByLabel('游戏', {exact: true}).selectOption('gomoku');
  await expect(page.getByRole('combobox', {name: '首盘黑棋', exact: true})).toBeVisible();
  await expect(page.getByRole('button', {name: '增加 Bot', exact: true})).toHaveCount(0);
  const options = await page.getByRole('combobox', {name: '首盘黑棋', exact: true}).locator('option').allTextContents();
  expect(options).toContain('Search'); expect(options).not.toContain('Safe');
  await page.locator('.import-disclosure > summary').click();
  await expect(page.getByLabel('Bot 所属游戏')).toHaveValue('gomoku');
  await page.getByLabel('Bot 文件').setInputFiles({name:'gomoku-probe.cpp',mimeType:'text/plain',buffer:source});
  await page.getByLabel('名称', {exact:true}).fill('五子棋验收 Bot');
  const upload = page.waitForResponse(r => r.url().endsWith('/api/v1/bots') && r.request().method()==='POST');
  await page.getByRole('button',{name:'导入 Bot',exact:true}).click();
  const bot = await (await upload).json(); expect(bot.game_id).toBe('gomoku');
  await expect(page.locator(`[data-bot-id="${bot.id}"]`)).toContainText('可运行',{timeout:20000});
  await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s => s.busy)).toBe(false);
  await page.getByRole('combobox',{name:'首盘黑棋',exact:true}).selectOption(bot.id);
  await page.getByRole('combobox',{name:'首盘白棋',exact:true}).selectOption(bot.id);
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:testInfo.outputPath('gomoku-home-mobile.png'),fullPage:true});
  const created = page.waitForResponse(r => r.url().endsWith('/api/v1/matches') && r.request().method()==='POST');
  await page.getByRole('button',{name:'开始对战',exact:true}).click();
  const run = await (await created).json(); expect(run.pair_runs).toHaveLength(2);
  await expect(page.getByRole('img',{name:/五子棋棋盘/})).toBeVisible();
  await expect(page.locator('.stone-label.black')).toHaveText('黑');
  await expect(page.locator('.stone-label.white')).toHaveText('白');
  await expect.poll(async () => (await request.get(`/api/v1/matches/${run.id}`)).json().then(r => r.pair.complete),{timeout:20000}).toBe(true);
  await page.reload(); await expect(page.locator('.spectator-stage')).toHaveAttribute('data-seq','0');
  await expect(page.getByRole('button',{name:'播放',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'下一帧',exact:true}).click();
  await expect(page.locator('.spectator-stage')).toHaveAttribute('data-seq','1');
  await page.getByLabel('显示落子顺序').check();
  await page.getByRole('button',{name:'最后一帧',exact:true}).click();
  await expect(page.locator('.result')).toContainText('连成五子');
  await expect(page.locator('.pair-score')).toContainText('1 : 1');
  expect(await page.evaluate(() => document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0,0));
  await page.screenshot({path:testInfo.outputPath('gomoku-end-mobile.png'),fullPage:true});
  await page.setViewportSize({width:1280,height:1000});
  await page.screenshot({path:testInfo.outputPath('gomoku-end-desktop.png'),fullPage:true});
  const replay = await (await request.get(`/api/v1/matches/${run.id}/frames`)).json();
  expect(replay.verified).toBe(true); expect(replay.frames.at(-1).state.winning_line).toHaveLength(5);
  await page.getByRole('link',{name:/第 2 盘/}).click();
  await expect(page).toHaveURL(new RegExp(run.pair_runs[1]+'$'));
  await expect(page.locator('.spectator-stage')).toHaveAttribute('data-seq','0');
  await page.getByRole('link',{name:'返回首页',exact:false}).click();
  await expect(page.getByLabel('游戏',{exact:true})).toHaveValue('gomoku');
  await page.getByText('开局设置',{exact:true}).click();
  await page.getByLabel('开局',{exact:true}).selectOption('library');
  await page.getByLabel('开局 Seed',{exact:true}).fill('5');
  const libraryCreated = page.waitForResponse(r => r.url().endsWith('/api/v1/matches') && r.request().method()==='POST');
  // Restored selection can point at baselines; choose the known probe explicitly.
  await page.getByRole('combobox',{name:'首盘黑棋',exact:true}).selectOption(bot.id);
  await page.getByRole('combobox',{name:'首盘白棋',exact:true}).selectOption(bot.id);
  await page.getByRole('button',{name:'开始对战',exact:true}).click();
  const libraryRun = await (await libraryCreated).json();
  await expect.poll(async () => (await request.get(`/api/v1/matches/${libraryRun.id}`)).json().then(r => r.pair.complete),{timeout:20000}).toBe(true);
  await page.reload(); await expect(page.getByRole('img',{name:/已落 3 子/})).toBeVisible();
  await page.getByRole('link',{name:'榜单',exact:true}).click();
  await expect(page.getByLabel('榜单游戏')).toHaveValue('gomoku');
  await expect(page.getByRole('columnheader',{name:'执黑',exact:true})).toBeVisible();
  const scores = await (await request.get('/api/v1/leaderboard?game_id=gomoku')).json();
  expect(scores.items.find((r:any) => r.id===bot.id).mean_score).toBe(.5);
  await page.screenshot({path:testInfo.outputPath('gomoku-leaderboard-desktop.png'),fullPage:true});
  expect(errors).toEqual([]);
});

test('五子棋基准完整对局不会超预算', async ({page,request},testInfo) => {
  await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s=>s.busy),{timeout:40000}).toBe(false);
  const bots=await (await request.get('/api/v1/bots?game_id=gomoku')).json();
  const ids=['Tactical','Search'].map(name=>bots.items.find((b:any)=>b.name===name && b.baseline && b.status==='ready').id);
  const response=await request.post('/api/v1/matches',{headers:{'X-Arena-Local':'1'},data:{bot_ids:ids,game_id:'gomoku',opening_mode:'library',map_seed:8}});
  expect(response.status()).toBe(202);const run=await response.json();
  await expect.poll(async () => (await request.get(`/api/v1/matches/${run.id}`)).json().then(r=>r.pair.complete),{timeout:40000}).toBe(true);
  for(const id of run.pair_runs) {
    const replay=await (await request.get(`/api/v1/matches/${id}/frames`)).json();
    expect(replay.verified).toBe(true); expect(replay.result.reason).toMatch(/five_in_row|board_full/);
    expect(replay.frames.flatMap((f:any)=>f.calls).every((c:any)=>c.fault===null)).toBe(true);
  }
  await page.goto(`/matches/${run.id}`);await page.getByRole('button',{name:'最后一帧',exact:true}).click();
  await page.screenshot({path:testInfo.outputPath('gomoku-baselines-end.png'),fullPage:true});
});
