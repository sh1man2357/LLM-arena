import { test, expect } from '@playwright/test';

test('Bot 信息编辑、筛选、参赛保护、批量删除与恢复', async ({page, request}, testInfo) => {
  const headers = {'X-Arena-Local': '1'};
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const prefix = `Bot管理-${Date.now()}`;
  const source = Buffer.from('#include "gomoku.hpp"\nnamespace bot { void init(uint64_t){} Action tick(const GameState&){return Action::resign();} }');
  const ids: string[] = [];
  let humanId: string | undefined;
  await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s => s.busy), {timeout: 40000}).toBe(false);
  for (let i = 0; i < 2; i++) {
    const response = await request.post('/api/v1/bots', {headers, multipart: {
      name: `${prefix}-${i}`, game_id: 'gomoku', file: {name: 'manage.cpp', mimeType: 'text/plain', buffer: source},
    }});
    expect(response.status()).toBe(202);
    const bot = await response.json(); ids.push(bot.id);
    await expect.poll(async () => (await request.get('/api/v1/bots?game_id=gomoku')).json().then(s => s.items.find((b: any) => b.id === bot.id)?.status)).toBe('ready');
    await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s => s.busy)).toBe(false);
  }
  try {
    const active = await request.post('/api/v1/human-matches', {headers, data: {bot_id: ids[0], human_slot: 0}});
    expect(active.status()).toBe(202); humanId = (await active.json()).id;
    await page.goto('/');
    await page.getByLabel('游戏', {exact: true}).selectOption('gomoku');
    const manager = page.locator('.bot-manager');
    const first = page.locator(`[data-bot-id="${ids[0]}"]`);
    await expect(first.getByRole('button', {name: /^删除 Bot/})).toBeDisabled();
    await expect(first).toContainText('使用中');
    await expect(page.getByRole('button', {name: '编辑 Bot Baseline', exact: true})).toHaveCount(0);
    await first.getByRole('button', {name: /^编辑 Bot/}).click();
    await page.getByLabel('Bot 名称', {exact: true}).fill(`${prefix}-新版`);
    await page.getByLabel('Bot 备注').fill('模型 X\n第 2 版策略，用于人机练习。');
    await page.setViewportSize({width: 1280, height: 1000});
    await page.screenshot({path: testInfo.outputPath('bot-edit-desktop.png'), fullPage: true});
    await page.getByRole('button', {name: '保存 Bot 信息', exact: true}).click();
    await expect(first).toContainText(`${prefix}-新版`);
    await expect(first).toContainText('第 2 版策略');
    const match = await (await request.get(`/api/v1/matches/${humanId}`)).json();
    expect(match.entrants[1].name).toBe(`${prefix}-0`);
    await expect(page.getByRole('combobox', {name: '首盘黑棋', exact: true}).locator(`option[value="${ids[0]}"]`)).toHaveText(`${prefix}-新版`);
    await expect.poll(async () => (await request.get(`/api/v1/matches/${humanId}`)).json().then(s => s.waiting_tick)).toBe(0);
    expect((await request.post(`/api/v1/matches/${humanId}/actions`, {headers, data: {tick: 0, action: 225}})).ok()).toBe(true);
    await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s => s.busy)).toBe(false);
    await expect(first.getByRole('button', {name: /^删除 Bot/})).toBeEnabled();
    await page.getByLabel('搜索 Bot', {exact: true}).fill(prefix);
    await page.getByLabel('Bot 状态', {exact: true}).selectOption('failed');
    await expect(manager).toContainText('没有符合筛选条件的 Bot');
    await page.getByLabel('Bot 状态', {exact: true}).selectOption('ready');
    await expect(manager.locator('[data-bot-id]')).toHaveCount(2);
    await page.setViewportSize({width: 390, height: 844});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path: testInfo.outputPath('bot-manager-mobile.png'), fullPage: true});
    page.once('dialog', dialog => dialog.dismiss());
    await first.getByRole('button', {name: /^删除 Bot/}).click();
    await expect(first).toBeVisible();
    page.once('dialog', dialog => dialog.accept());
    await first.getByRole('button', {name: /^删除 Bot/}).click();
    await expect(first).toHaveCount(0);
    await expect(page.getByRole('combobox', {name: '首盘黑棋', exact: true}).locator(`option[value="${ids[0]}"]`)).toHaveCount(0);
    await page.getByRole('button', {name: 'Bot 回收站', exact: true}).click();
    await expect(first).toContainText('第 2 版策略');
    await first.getByRole('button', {name: /^恢复 Bot/}).click();
    await expect(first).toHaveCount(0);
    await page.getByRole('button', {name: '可用列表', exact: true}).click();
    await expect(manager.locator('[data-bot-id]')).toHaveCount(2);
    await page.getByRole('checkbox', {name: '选择本页 Bot', exact: true}).check();
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', {name: '删除所选 Bot', exact: true}).click();
    await expect(manager.locator('[data-bot-id]')).toHaveCount(0);
    await page.getByRole('button', {name: 'Bot 回收站', exact: true}).click();
    await expect(manager.locator('[data-bot-id]')).toHaveCount(2);
    await page.getByRole('checkbox', {name: '选择本页 Bot', exact: true}).check();
    await page.getByRole('button', {name: '恢复所选 Bot', exact: true}).click();
    await expect(manager.locator('[data-bot-id]')).toHaveCount(0);
    await page.reload();
    await page.getByLabel('搜索 Bot', {exact: true}).fill(prefix);
    await expect(first).toContainText('第 2 版策略');
    await expect(manager.locator('[data-bot-id]')).toHaveCount(2);
    await first.getByRole('button', {name: /^编辑 Bot/}).click();
    await page.getByLabel('Bot 名称', {exact: true}).fill('不会保存');
    await page.getByRole('button', {name: '取消编辑', exact: true}).click();
    await expect(first).toContainText(`${prefix}-新版`);
    await page.getByLabel('游戏', {exact: true}).selectOption('bomberman');
    await expect(page.locator(`[data-bot-id="${ids[0]}"]`)).toHaveCount(0);
    expect(errors).toEqual([]);
  } finally {
    if (humanId) {
      const row = await (await request.get(`/api/v1/matches/${humanId}`)).json();
      if (row.status === 'running' && Number.isInteger(row.waiting_tick)) {
        await request.post(`/api/v1/matches/${humanId}/actions`, {headers, data: {tick: row.waiting_tick, action: 225}});
      }
    }
  }
});

test('Bot 分页切换清除选择，筛选和删除后保持有效页', async ({page}) => {
  const bots = Array.from({length: 21}, (_, i) => ({id: `page-${i}`, name: `分页 Bot ${i}`,
    status: 'ready', baseline: false, created: '2026-10-18T00:00:00Z'}));
  await page.route('**/api/v1/bots', route => route.fulfill({json: {items: bots}}));
  await page.route('**/api/v1/bots/manage', async route => {
    const ids = route.request().postDataJSON().ids as string[];
    for (const id of ids) { const index = bots.findIndex(b => b.id === id); if (index >= 0) bots.splice(index, 1); }
    await route.fulfill({json: {changed: ids.length}});
  });
  await page.goto('/');
  const manager = page.locator('.bot-manager');
  await expect(manager.locator('[data-bot-id]')).toHaveCount(20);
  await page.getByRole('checkbox', {name: '选择本页 Bot', exact: true}).check();
  await expect(manager).toContainText('已选 20 个');
  await page.getByRole('button', {name: '下一页 Bot', exact: true}).click();
  await expect(manager.locator('[data-bot-id]')).toHaveCount(1);
  await expect(manager).toContainText('已选 0 个');
  page.once('dialog', dialog => dialog.accept());
  await manager.getByRole('button', {name: '删除 Bot 分页 Bot 20', exact: true}).click();
  await expect(manager.locator('[data-bot-id]')).toHaveCount(20);
  await expect(page.getByRole('button', {name: '上一页 Bot', exact: true})).toBeDisabled();
  await page.getByLabel('搜索 Bot', {exact: true}).fill('分页 Bot 19');
  await expect(manager.locator('[data-bot-id]')).toHaveCount(1);
});
