import { test, expect } from '@playwright/test';

test('记录分页：切页清除选择，删除末页最后一条后返回有效页', async ({page}) => {
  let rows = Array.from({length: 21}, (_, i) => ({id: `page-${i}`, title: `分页记录 ${i}`, status: 'completed',
    entrants: [], ticks: 0, verified: true, result: null, created: new Date().toISOString(), map_seed: i}));
  await page.route(/\/api\/v1\/matches\?/, async route => {
    const params = new URL(route.request().url()).searchParams;
    const offset = Number(params.get('offset'));
    await route.fulfill({json: {items: rows.slice(offset, offset + 20), total: rows.length}});
  });
  await page.route('**/api/v1/matches/manage', async route => {
    const body = route.request().postDataJSON();
    expect(body.action).toBe('trash');
    expect(body.ids).toEqual(['page-20']);
    rows = rows.filter(row => !body.ids.includes(row.id));
    await route.fulfill({json: {changed: 1}});
  });
  await page.goto('/');
  const history = page.locator('#history');
  await expect(history.locator('[data-run-id]')).toHaveCount(20);
  await page.getByRole('checkbox', {name: '选择本页', exact: true}).check();
  await expect(history).toContainText('已选 20 条');
  await page.getByRole('button', {name: '下一页', exact: true}).click();
  await expect(history.locator('[data-run-id]')).toHaveCount(1);
  await expect(history).toContainText('已选 0 条');
  await expect(page.getByRole('button', {name: '删除所选', exact: true})).toBeDisabled();
  await page.getByRole('checkbox', {name: '选择本页', exact: true}).check();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: '删除所选', exact: true}).click();
  await expect(history.locator('[data-run-id]')).toHaveCount(20);
  await expect(history.locator('.pagination')).toContainText('1～20 / 20');
  await expect(page.getByRole('button', {name: '上一页', exact: true})).toBeDisabled();
  await expect(page.getByRole('button', {name: '下一页', exact: true})).toBeDisabled();
});

test('记录管理：运行保护、重命名、筛选、删除确认、批量恢复与清空', async ({page, request}, testInfo) => {
  test.setTimeout(150000);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s => s.busy), {timeout: 40000}).toBe(false);
  const bots = (await (await request.get('/api/v1/bots?game_id=bomberman')).json()).items;
  const bot = bots.find((b: any) => !b.baseline && b.status === 'ready') || bots.find((b: any) => b.status === 'ready');
  expect(bot).toBeTruthy();
  const before = (await (await request.get('/api/v1/leaderboard')).json()).valid_matches;
  const name = `记录管理-${Date.now()}`;
  const ids: string[] = [];
  for (let i = 0; i < 2; i++) {
    const response = await request.post('/api/v1/matches', {headers: {'X-Arena-Local': '1'}, data: {bot_ids: [bot.id, bot.id], map_seed: 1}});
    expect(response.status()).toBe(202);
    const run = await response.json(); ids.push(run.id);
    if (i === 0) {
      await page.goto('/');
      await page.getByLabel('搜索对局', {exact: true}).fill(run.id);
      const row = page.locator(`[data-run-id="${run.id}"]`);
      await expect(row.getByRole('button', {name: /^删除对局/})).toBeDisabled();
      await expect(row.getByRole('checkbox')).toBeDisabled();
      await row.getByRole('button', {name: /^重命名对局/}).click();
      await page.getByLabel('对局名称', {exact: true}).fill(`${name}-${i}`);
      await page.getByRole('button', {name: '保存名称', exact: true}).click();
      await expect(row).toContainText(`${name}-${i}`);
    } else {
      expect((await request.patch(`/api/v1/matches/${run.id}`, {headers: {'X-Arena-Local': '1'}, data: {title: `${name}-${i}`}})).ok()).toBe(true);
    }
    await expect.poll(async () => (await request.get(`/api/v1/matches/${run.id}`)).json().then(r => r.status), {timeout: 40000}).toBe('completed');
    await expect.poll(async () => (await request.get('/api/v1/status')).json().then(s => s.busy)).toBe(false);
  }
  await page.getByLabel('搜索对局', {exact: true}).fill(name);
  await page.getByLabel('对局状态', {exact: true}).selectOption('completed');
  const history = page.locator('#history');
  await expect(history.locator('[data-run-id]')).toHaveCount(2);
  await page.setViewportSize({width: 1280, height: 1100});
  await history.screenshot({path: testInfo.outputPath('history-desktop.png')});
  await page.setViewportSize({width: 390, height: 844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await history.screenshot({path: testInfo.outputPath('history-mobile.png')});
  page.once('dialog', dialog => dialog.dismiss());
  await page.locator(`[data-run-id="${ids[0]}"]`).getByRole('button', {name: /^删除对局/}).click();
  await expect(history.locator('[data-run-id]')).toHaveCount(2);
  page.once('dialog', dialog => dialog.accept());
  await page.locator(`[data-run-id="${ids[0]}"]`).getByRole('button', {name: /^删除对局/}).click();
  await expect(history.locator('[data-run-id]')).toHaveCount(1);
  await page.getByRole('checkbox', {name: '选择本页', exact: true}).check();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: '删除所选', exact: true}).click();
  await expect(history.locator('[data-run-id]')).toHaveCount(0);
  expect((await (await request.get('/api/v1/leaderboard')).json()).valid_matches).toBe(before);
  await page.getByRole('button', {name: '回收站', exact: true}).click();
  await expect(history.locator('[data-run-id]')).toHaveCount(2);
  await page.reload();
  await page.getByLabel('搜索对局', {exact: true}).fill(name);
  await page.getByRole('button', {name: '回收站', exact: true}).click();
  await expect(history.locator('[data-run-id]')).toHaveCount(2);
  await page.getByRole('checkbox', {name: '选择本页', exact: true}).check();
  await page.getByRole('button', {name: '恢复所选', exact: true}).click();
  await expect(history.locator('[data-run-id]')).toHaveCount(0);
  expect((await (await request.get('/api/v1/leaderboard')).json()).valid_matches).toBe(before + 2);
  expect((await (await request.get(`/api/v1/matches/${ids[0]}/frames`)).json()).verified).toBe(true);
  await page.getByRole('button', {name: '全部记录', exact: true}).click();
  await expect(history.locator('[data-run-id]')).toHaveCount(2);
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: '清空已结束记录', exact: true}).click();
  await expect(history.locator('[data-run-id]')).toHaveCount(0);
  expect((await (await request.get('/api/v1/leaderboard')).json()).valid_matches).toBe(before);
  await page.getByLabel('搜索对局', {exact: true}).fill('不存在的记录名称');
  await expect(history).toContainText('没有符合筛选条件的对局');
  expect(errors).toEqual([]);
});
