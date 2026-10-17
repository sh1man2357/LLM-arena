import { test, expect } from '@playwright/test';

test('五子棋人机入口、落子、刷新续玩、认输和录像', async ({page, request}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const headers = {'X-Arena-Local': '1'};
  const runs: string[] = [];
  await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s => s.busy), {timeout: 40000}).toBe(false);
  const source = '#include "gomoku.hpp"\nnamespace bot { void init(uint64_t){} Action tick(const GameState& s){return {int(s.move_count/2),0};} }';
  const imported = await request.post('/api/v1/bots', {headers, multipart: {
    name: '人机入口验收 Bot', game_id: 'gomoku',
    file: {name: 'human-probe.cpp', mimeType: 'text/plain', buffer: Buffer.from(source)},
  }});
  expect(imported.status()).toBe(202);
  const bot = await imported.json();
  await expect.poll(async () => (await request.get('/api/v1/bots?game_id=gomoku')).json().then(s => s.items.find((b: any) => b.id === bot.id)?.status)).toBe('ready');
  await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s => s.busy)).toBe(false);
  const before = await (await request.get('/api/v1/leaderboard?game_id=gomoku')).json();
  async function start(slot: number) {
    await page.goto('/');
    await page.getByLabel('游戏', {exact: true}).selectOption('gomoku');
    await page.getByLabel('对战模式').selectOption('human');
    await page.getByLabel('对手 Bot').selectOption(bot.id);
    await page.getByLabel('你的执子').selectOption(String(slot));
    await expect(page.getByText('开局设置', {exact: true})).toHaveCount(0);
    const created = page.waitForResponse(r => r.url().endsWith('/api/v1/human-matches') && r.request().method() === 'POST');
    await page.getByRole('button', {name: '开始对战', exact: true}).click();
    const run = await (await created).json();
    runs.push(run.id);
    expect(run.mode).toBe('human');
    expect(run.pair_runs).toBeNull();
    return run;
  }
  try {
    const run = await start(0);
    await expect(page.getByRole('button', {name: 'A15，落子', exact: true})).toBeEnabled();
    await expect(page.getByLabel('时间轴')).toHaveCount(0);
    await page.getByRole('button', {name: 'A15，落子', exact: true}).click();
    await expect(page.getByRole('button', {name: 'B15，落子', exact: true})).toBeEnabled();
    await expect(page.getByRole('img', {name: /已落 2 子/})).toBeVisible();
    await page.reload();
    await expect(page.getByRole('button', {name: 'B15，落子', exact: true})).toBeEnabled();
    await expect(page.getByRole('button', {name: 'A15，已有棋子', exact: true})).toBeDisabled();
    await page.screenshot({path: testInfo.outputPath('human-desktop.png'), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path: testInfo.outputPath('human-mobile.png'), fullPage: true});
    for (const column of ['B', 'C', 'D', 'E']) {
      const cell = page.getByRole('button', {name: `${column}15，落子`, exact: true});
      await expect(cell).toBeEnabled();
      if (column === 'E') { await cell.focus(); await cell.press('Enter'); }
      else await cell.click();
    }
    await expect(page.locator('.result')).toContainText('连成五子');
    await expect(page.locator('.gomoku-input')).toHaveCount(0);
    const replay = await (await request.get(`/api/v1/matches/${run.id}/frames`)).json();
    expect(replay.verified).toBe(true);
    expect(replay.result.winner).toBe(0);
    expect(replay.frames.at(-1).state.winning_line).toHaveLength(5);
    await page.reload();
    await expect(page.locator('.spectator-stage')).toHaveAttribute('data-seq', '0');
    await page.getByRole('button', {name: '最后一帧', exact: true}).click();
    await expect(page.locator('.result')).toContainText('连成五子');
    const againResponse = page.waitForResponse(r => r.url().endsWith(`/matches/${run.id}/rerun`));
    await page.getByRole('button', {name: '再来一局'}).click();
    const again = await (await againResponse).json();
    runs.push(again.id);
    expect(again.human_slot).toBe(0);
    await expect(page.getByRole('button', {name: '认输', exact: true})).toBeEnabled();
    await page.getByRole('button', {name: '认输', exact: true}).click();
    await expect(page.locator('.result')).toContainText('认输');
    await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s => s.busy)).toBe(false);

    const white = await start(1);
    await expect(page.getByRole('button', {name: '认输', exact: true})).toBeEnabled();
    await expect(page.getByRole('img', {name: /已落 1 子/})).toBeVisible();
    await page.getByRole('button', {name: '认输', exact: true}).click();
    await expect(page.locator('.result')).toContainText('认输');
    const done = await (await request.get(`/api/v1/matches/${white.id}`)).json();
    expect(done.result.winner).toBe(0);
    expect(await (await request.get('/api/v1/leaderboard?game_id=gomoku')).json()).toEqual(before);
    await page.goto('/');
    await expect(page.locator(`[data-run-id="${white.id}"]`)).toContainText('人机对战 · 不计榜单');
    expect(errors).toEqual([]);
  } finally {
    // Release this test's compute slot if an assertion failed mid-game.
    for (const id of runs) {
      const row = await (await request.get(`/api/v1/matches/${id}`)).json();
      if (row.status === 'running' && Number.isInteger(row.waiting_tick)) {
        await request.post(`/api/v1/matches/${id}/actions`, {headers, data: {tick: row.waiting_tick, action: 225}});
      }
    }
  }
});
