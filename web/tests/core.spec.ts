import { test, expect } from '@playwright/test';

const source = Buffer.from('#include "arena.hpp"\nnamespace bot { void init(uint64_t){} Action tick(const GameState&){return Action::WAIT;} }');

test('八人各自为战：增减槽位、直播、排名与录像', async ({page, request}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s => s.busy), {timeout: 40000}).toBe(false);
  const bots = await (await request.get('/api/v1/bots?game_id=bomberman')).json();
  expect(bots.items.filter((b:any)=>b.baseline)).toHaveLength(1);
  const uploaded = await request.post('/api/v1/bots', {headers:{'X-Arena-Local':'1'}, multipart:{name:'Safety probe', file:{name:'bot.cpp',mimeType:'text/plain',buffer:source}}});
  const safe = await uploaded.json();
  await expect.poll(async () => (await (await request.get('/api/v1/bots?game_id=bomberman')).json()).items.find((b:any)=>b.id===safe.id)?.status,{timeout:40000}).toBe('ready');
  await page.goto('/');
  await expect(page.getByRole('button', {name: '移除 Bot 0'})).toBeDisabled();
  await page.getByRole('button', {name: '增加 Bot', exact: true}).click();
  await expect(page.getByRole('combobox', {name: 'Bot 2', exact: true})).toBeVisible();
  await page.getByRole('button', {name: '移除 Bot 1', exact: true}).click();
  await expect(page.locator('.slot-picker')).toHaveCount(2);
  for (let count = 2; count < 8; count++) await page.getByRole('button', {name: '增加 Bot', exact: true}).click();
  await expect(page.getByRole('button', {name: '增加 Bot', exact: true})).toBeDisabled();
  for (let slot = 0; slot < 8; slot++) await page.getByRole('combobox', {name: `Bot ${slot}`, exact: true}).selectOption(safe.id);
  await page.setViewportSize({width: 390, height: 844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: testInfo.outputPath('eight-player-picker-mobile.png'), fullPage: true});
  const created = page.waitForResponse(r => r.url().endsWith('/api/v1/matches') && r.request().method() === 'POST');
  await page.getByRole('button', {name: '开始对战', exact: true}).click();
  const response = await created;
  expect(response.status()).toBe(202);
  const run = await response.json();
  expect(run.entrants.map((e: any) => e.slot)).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
  await expect(page.locator('.player-card')).toHaveCount(8);
  await page.setViewportSize({width: 1280, height: 1000});
  await page.screenshot({path: testInfo.outputPath('eight-player-live-desktop.png'), fullPage: true});
  expect(await page.locator('.player-card').evaluateAll(cards => new Set(cards.map(card => getComputedStyle(card).borderColor)).size)).toBe(8);
  await expect.poll(async () => (await request.get(`/api/v1/matches/${run.id}`)).json().then(r => r.status), {timeout: 40000}).toBe('completed');
  await expect(page.getByRole('button', {name: '回到最新'})).toBeHidden();
  await page.getByRole('button', {name: '最后一帧', exact: true}).click();
  await expect(page.getByRole('heading', {name: '平局', exact: true})).toBeVisible();
  await expect(page.getByRole('list', {name: '本局排名'}).locator('li')).toHaveCount(8);
  const recording = await (await request.get(`/api/v1/matches/${run.id}/frames`)).json();
  expect(recording.verified).toBe(true);
  expect(recording.frames[0].state.players).toHaveLength(8);
  expect(recording.result.groups).toEqual([[0, 1, 2, 3, 4, 5, 6, 7]]);
  expect(recording.rules.scoring_version).toBe(2);
  expect(recording.result.players.map((p: any) => p.score)).toEqual(Array(8).fill(500));
  await expect(page.locator('.player-card').first()).toContainText('500 分 · 击杀 0');
  await expect(page.getByRole('list', {name: '本局排名'}).locator('li').first()).toContainText('500 分 · 生存 500 + 击杀 0');
  await page.reload();
  await expect(page.locator('.player-card')).toHaveCount(8);
  await page.getByRole('button', {name: '最后一帧', exact: true}).click();
  await page.screenshot({path: testInfo.outputPath('eight-player-recording-desktop.png'), fullPage: true});
  await page.setViewportSize({width: 390, height: 844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: testInfo.outputPath('eight-player-recording-mobile.png'), fullPage: true});
  expect(errors).toEqual([]);
});

test('仅一个可运行 Bot 时可默认自对战并查看录像', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const bots = await (await request.get('/api/v1/bots?game_id=bomberman')).json();
  const bot = bots.items.find((b: any) => b.status === 'ready');
  expect(bot).toBeTruthy();
  await page.route('**/api/v1/bots', route => route.fulfill({json: {items: [bot]}}));
  await page.goto('/');
  await expect(page.getByRole('combobox', {name: 'Bot 0', exact: true})).toHaveValue(bot.id);
  await expect(page.getByRole('combobox', {name: 'Bot 1', exact: true})).toHaveValue(bot.id);
  await expect(page.getByRole('button', {name: '开始对战', exact: true})).toBeEnabled();
  const created = page.waitForResponse(r => r.url().endsWith('/api/v1/matches') && r.request().method() === 'POST');
  await page.getByRole('button', {name: '开始对战', exact: true}).click();
  const response = await created;
  expect(response.status()).toBe(202);
  const run = await response.json();
  expect(run.entrants.map((e: any) => [e.id, e.slot])).toEqual([[bot.id, 0], [bot.id, 1]]);
  await expect(page.locator('.player-card')).toHaveCount(2);
  for (const card of await page.locator('.player-card').all()) await expect(card).toContainText(bot.name);
  await expect.poll(async () => (await request.get(`/api/v1/matches/${run.id}`)).json().then(r => r.status), {timeout: 40000}).toBe('completed');
  await page.reload();
  await expect(page.locator('.player-card')).toHaveCount(2);
  const recording = await (await request.get(`/api/v1/matches/${run.id}/frames`)).json();
  expect(recording.verified).toBe(true);
  expect(recording.frames.length).toBeGreaterThan(1);
  expect(errors).toEqual([]);
});

test('导入、真实运行、暂停回看、保存录像和榜单', async ({ page, request }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', {name: '对战', exact: true})).toBeVisible();
  await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s => s.busy), {timeout: 20000}).toBe(false);
  await expect(page.getByLabel('Bot 文件')).toBeHidden();
  await expect(page.getByLabel('地图 Seed', {exact: true})).toBeHidden();
  await page.screenshot({path: testInfo.outputPath('home-desktop.png'), fullPage: true});
  await page.setViewportSize({width: 390, height: 844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: testInfo.outputPath('home-mobile.png'), fullPage: true});
  await page.locator('.import-disclosure > summary').focus();
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Bot 文件')).toBeVisible();
  await page.getByText('地图设置', {exact: true}).click();
  await expect(page.getByLabel('地图 Seed', {exact: true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: testInfo.outputPath('home-import-mobile.png'), fullPage: true});
  await page.getByText('地图设置', {exact: true}).click();
  await page.setViewportSize({width: 1280, height: 900});
  const ids: string[] = [];
  for (let slot = 0; slot < 2; slot++) {
    await page.getByLabel('Bot 文件').setInputFiles({name: `wait-${slot}.cpp`, mimeType: 'text/plain', buffer: source});
    await page.getByLabel('名称', {exact: true}).fill(`观赛检查 ${slot}`);
    const response = page.waitForResponse(r => r.url().endsWith('/api/v1/bots') && r.request().method() === 'POST');
    await page.getByRole('button', {name: '导入 Bot', exact: true}).click();
    const bot = await (await response).json();
    ids.push(bot.id);
    await expect(page.locator(`[data-bot-id="${bot.id}"]`)).toContainText('可运行', {timeout: 20000});
    await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s => s.busy)).toBe(false);
  }
  await page.getByRole('combobox', {name: 'Bot 0', exact: true}).selectOption(ids[0]);
  await page.getByRole('combobox', {name: 'Bot 1', exact: true}).selectOption(ids[0]);
  await expect(page.getByRole('button', {name: '开始对战', exact: true})).toBeEnabled();
  await page.getByRole('combobox', {name: 'Bot 1', exact: true}).selectOption(ids[1]);
  await page.getByText('地图设置', {exact: true}).click();
  await page.getByLabel('地图 Seed', {exact: true}).fill('1');
  const created = page.waitForResponse(r => r.url().endsWith('/api/v1/matches') && r.request().method() === 'POST');
  await page.getByRole('button', {name: '开始对战', exact: true}).click();
  const run = await (await created).json();
  await expect(page).toHaveURL(new RegExp(`/matches/${run.id}$`));
  const stage = page.locator('.spectator-stage');
  await expect(page.locator('canvas')).toBeVisible();
  await expect.poll(async () => Number(await stage.getAttribute('data-frame-count'))).toBeGreaterThan(3);
  await page.getByRole('button', {name: '回到初始帧'}).click();
  await expect(stage).toHaveAttribute('data-seq', '0');
  await page.getByRole('button', {name: '播放', exact: true}).click();
  await expect.poll(async () => Number(await stage.getAttribute('data-seq'))).toBeGreaterThan(0);
  await page.getByRole('button', {name: '暂停', exact: true}).click();
  const frozen = await stage.getAttribute('data-seq');
  await expect.poll(async () => (await request.get(`/api/v1/matches/${run.id}`)).json().then(r => r.ticks)).toBeGreaterThan(Number(frozen) + 4);
  await expect(stage).toHaveAttribute('data-seq', frozen!);
  const received = Number(await stage.getAttribute('data-frame-count'));
  await page.context().setOffline(true);
  try {
    // Chrome offline emulation blocks new HTTP reads but can keep an existing SSE open.
    await expect(page.getByRole('alert')).toContainText('无法连接本地服务');
    await expect(stage).toHaveAttribute('data-seq', frozen!);
  } finally {
    await page.context().setOffline(false);
  }
  await expect.poll(async () => Number(await stage.getAttribute('data-frame-count'))).toBeGreaterThan(received);
  await page.screenshot({path: testInfo.outputPath('live-desktop.png'), fullPage: true});
  await page.getByRole('button', {name: '回到最新'}).click();
  await expect(page.getByRole('button', {name: '暂停', exact: true})).toBeVisible();
  await expect.poll(async () => (await request.get(`/api/v1/matches/${run.id}`)).json().then(r => r.status), {timeout: 40000}).toBe('completed');
  await expect(page.getByRole('button', {name: '回到最新'})).toBeHidden();
  await page.getByRole('button', {name: '最后一帧', exact: true}).click();
  await expect(page.getByRole('heading', {name: '平局', exact: true})).toBeVisible();
  const saved = (await (await request.get(`/api/v1/matches/${run.id}/frames`)).json()).frames.length;
  expect(saved).toBe(501);
  await page.reload();
  await expect(stage).toHaveAttribute('data-seq', '0');
  await page.getByRole('button', {name: '下一帧'}).click();
  await expect(stage).toHaveAttribute('data-seq', '1');
  await page.locator('canvas').click();
  await page.keyboard.press('ArrowRight');
  await expect(stage).toHaveAttribute('data-seq', '2');
  await page.getByRole('button', {name: '全屏', exact: true}).click();
  await expect.poll(() => page.evaluate(() => !!document.fullscreenElement)).toBe(true);
  await page.getByRole('button', {name: '全屏', exact: true}).click();
  await expect.poll(() => page.evaluate(() => !!document.fullscreenElement)).toBe(false);
  await page.getByLabel('倍速', {exact: true}).selectOption('4');
  await page.setViewportSize({width: 390, height: 844});
  await expect(page.locator('canvas')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: testInfo.outputPath('recording-mobile.png'), fullPage: true});
  await page.getByRole('link', {name: '返回首页', exact: false}).click();
  await expect(page.locator(`.run-list a[href="/matches/${run.id}"]`)).toBeVisible();
  await page.getByRole('link', {name: '榜单', exact: true}).click();
  await expect(page.getByRole('heading', {name: '本地榜单'})).toBeVisible();
  const rankings = await (await request.get('/api/v1/leaderboard')).json();
  const own = rankings.items.filter((row: any) => ids.includes(row.id));
  expect(own).toHaveLength(2);
  expect(own.map((row: any) => [row.rank, row.rating, row.matches, row.draws, row.mean_score])).toEqual([[null, null, 1, 1, .5], [null, null, 1, 1, .5]]);
  await page.screenshot({path: testInfo.outputPath('leaderboard-mobile.png'), fullPage: true});
  expect(errors).toEqual([]);
});

test('导入失败与已删除页面、API', async ({page, request}) => {
  await page.goto('/');
  await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s => s.busy), {timeout: 40000}).toBe(false);
  await page.locator('.import-disclosure > summary').click();
  await page.getByLabel('Bot 文件').setInputFiles({name: 'broken.cpp', mimeType: 'text/plain', buffer: Buffer.from('not C++')});
  const response = page.waitForResponse(r => r.url().endsWith('/api/v1/bots') && r.request().method() === 'POST');
  await page.getByRole('button', {name: '导入 Bot', exact: true}).click();
  const bot = await (await response).json();
  const row = page.locator(`[data-bot-id="${bot.id}"]`);
  await expect(row).toContainText('失败', {timeout: 20000});
  await expect(row.getByText('编译日志', {exact: true})).toBeVisible();
  expect(await page.getByRole('combobox', {name: 'Bot 0', exact: true}).locator(`option[value="${bot.id}"]`).count()).toBe(0);
  for (const path of ['/manage', '/tournaments', '/entrants']) {
    await page.goto(path);
    await expect(page.getByRole('heading', {name: '页面不存在'})).toBeVisible();
  }
  for (const path of ['sessions', 'submissions', 'tournaments', 'backups', 'jobs', 'imports', 'exports/old']) {
    expect((await request.get('/api/v1/' + path)).status()).toBe(404);
  }
});

test('真实棋盘的脚下炸弹、爆炸与终局画面', async ({page, request}, testInfo) => {
  const bots = await (await request.get('/api/v1/bots?game_id=bomberman')).json();
  const baseline = bots.items.find((bot:any)=>bot.baseline && bot.status==='ready');
  const entrants = [baseline, baseline];
  expect(entrants.every(Boolean)).toBe(true);
  const created = await request.post('/api/v1/matches', {
    headers: {'X-Arena-Local': '1'}, data: {bot_ids: entrants.map(bot => bot.id), map_seed: 1},
  });
  expect(created.status()).toBe(202);
  const run = await created.json();
  await expect.poll(async () => (await (await request.get(`/api/v1/matches/${run.id}`)).json()).status, {timeout:40000}).toBe('completed');
  const replay = await (await request.get(`/api/v1/matches/${run.id}/frames`)).json();
  expect(replay.verified).toBe(true);
  const bombSeq = replay.frames.findIndex((frame: any) => frame.state.bombs.some((bomb: any) => frame.state.players.some((player: any) => player.x === bomb.x && player.y === bomb.y)));
  const blastSeq = replay.frames.findIndex((frame: any) => frame.visual.coverage.length > 0);
  expect(bombSeq).toBeGreaterThan(0);
  expect(blastSeq).toBeGreaterThan(bombSeq);
  await page.setViewportSize({width: 1280, height: 900});
  await page.goto(`/matches/${run.id}`);
  const stage = page.locator('.spectator-stage');
  await expect(stage).toHaveAttribute('data-seq', '0');
  for (let seq = 0; seq < bombSeq; seq++) await page.getByRole('button', {name: '下一帧'}).click();
  await expect(stage).toHaveAttribute('data-seq', String(bombSeq));
  await page.screenshot({path: testInfo.outputPath('arena-bombs-desktop.png'), fullPage: true});
  for (let seq = bombSeq; seq < blastSeq; seq++) await page.getByRole('button', {name: '下一帧'}).click();
  await expect(stage).toHaveAttribute('data-seq', String(blastSeq));
  await page.screenshot({path: testInfo.outputPath('arena-blast-desktop.png'), fullPage: true});
  await page.getByRole('button', {name: '最后一帧'}).click();
  await expect(stage).toHaveAttribute('data-seq', String(replay.frames.length - 1));
  // A blast can happen before anyone is eliminated; verify the recorded terminal state.
  if (replay.frames.at(-1).state.players.some((player: any) => !player.alive)) {
    await expect(page.locator('.player-state').filter({hasText: '出局'}).first()).toBeVisible();
  }
  await page.setViewportSize({width: 390, height: 844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: testInfo.outputPath('arena-end-mobile.png'), fullPage: true});
});
