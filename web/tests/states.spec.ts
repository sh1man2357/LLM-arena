import { test, expect, type Page } from '@playwright/test';
import { resolve } from 'node:path';

const output = resolve(process.env.ARENA_STATE_EVIDENCE || '../artifacts/work/checks/visual/read-states');
const widths = [390, 768, 1280, 1440];
const cases = [
  ['hall', '/', /\/api\/v1\/matches\?/, '正在读取对局记录', '.match-row'],
  ['batches', '/tournaments', /\/api\/v1\/tournaments$/, '正在读取比赛批次', '.batch-card'],
  ['entrants', '/entrants', /\/api\/v1\/entrants$/, '正在读取参赛者', '.entrant-card'],
  ['batch', '/tournaments/reference', /\/api\/v1\/tournaments\/reference$/, '正在读取批次', '.ranking-row'],
  ['viewer', '/matches/reference-chain', /\/api\/v1\/matches\/reference-chain(?:\/frames)?$/, '正在准备观赛画面', 'canvas'],
  ['manage', '/manage', /\/api\/v1\/jobs$/, '正在读取工作台记录', '.source-workspace'],
] as const;

async function pictures(page: Page, name: string) {
  for (const width of widths) {
    await page.setViewportSize({width, height: 1000});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({path: resolve(output, `${name}-${width}.png`), fullPage: true});
  }
}

for (const [name, path, request, loading, content] of cases) {
  test(`${name}: delayed real reads show loading, then confirmed content`, async ({page}) => {
    let release!: () => void;
    const gate = new Promise<void>(done => { release = done; });
    await page.route(request, async route => { await gate; await route.continue().catch(() => {}); });
    try {
      await page.goto(path, {waitUntil: 'domcontentloaded'});
      await expect(page.getByRole('status').getByRole('heading', {name: loading, exact: true})).toBeVisible();
      if (name === 'manage') await expect(page.getByText('尚无作业。编译、单局、批次与导入会显示在这里。')).toHaveCount(0);
      await pictures(page, `${name}-loading`);
    } finally { release(); }
    await expect(page.locator(content).first()).toBeVisible();
    await expect(page.getByRole('heading', {name: loading, exact: true})).toHaveCount(0);
  });
  test(`${name}: failed read has a local recovery action`, async ({page}) => {
    await page.route(request, route => route.fulfill({status: 503, contentType: 'application/json', body: JSON.stringify({message: '本轮注入：读取暂不可用'})}));
    await page.goto(path);
    await expect(page.getByRole('alert').getByRole('heading', {name: '暂时无法读取数据'})).toBeVisible();
    await pictures(page, `${name}-unavailable`);
    await page.unroute(request);
    const navigation = page.url();
    await page.getByRole('button', {name: '重试读取', exact: true}).click();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.locator(content).first()).toBeVisible();
    expect(page.url().split('?')[0]).toBe(navigation.split('?')[0]);
  });
}

test('empty filters can be cleared and a failed new filter never shows old results', async ({page}) => {
  await page.goto('/');
  await expect(page.locator('.match-row').first()).toBeVisible();
  const query = '没有这个参赛者-读取状态验收';
  const request = /\/api\/v1\/matches\?.*q=/;
  await page.route(request, route => {
    if (new URL(route.request().url()).searchParams.get('q') === query) return route.fulfill({status: 503, contentType: 'application/json', body: '{"message":"新筛选读取失败"}'});
    return route.continue();
  });
  await page.getByLabel('搜索对局').fill(query);
  await expect(page.getByRole('alert')).toContainText('新筛选读取失败');
  await expect(page.locator('.match-row')).toHaveCount(0);
  await page.unroute(request);
  let release!: () => void;
  const gate = new Promise<void>(done => { release = done; });
  await page.route(request, async route => { await gate; await route.continue().catch(() => {}); });
  try {
    await page.getByRole('button', {name:'重试读取'}).click();
    await expect(page.getByRole('heading', {name:'正在读取对局记录'})).toBeVisible();
    await expect(page.locator('.match-row')).toHaveCount(0);
    await expect(page.locator('.feature-match')).toHaveCount(0);
  } finally { release(); }
  await expect(page.getByRole('heading', {name:'没有符合筛选条件的对局'})).toBeVisible();
  await pictures(page, 'hall-empty-filter');
  await page.unroute(request);
  await page.getByRole('button', {name:'清除筛选', exact:true}).click();
  await expect(page.getByLabel('搜索对局')).toHaveValue('');
  await expect(page.locator('.match-row').first()).toBeVisible();
});

test('actual missing resources distinguish absence and provide a return path', async ({page}) => {
  for (const [name, path] of [['viewer','/matches/read-state-absent'], ['batch','/tournaments/read-state-absent'], ['entrant','/entrants/read-state-absent']]) {
    await page.goto(path);
    await expect(page.getByRole('alert').getByRole('heading', {name:'没有找到这份资料'})).toBeVisible();
    await expect(page.locator('canvas,.ranking-row,.match-row')).toHaveCount(0);
    await pictures(page, `${name}-missing`);
    await page.getByRole('link', {name:'回到比赛大厅', exact:true}).click();
    await expect(page.locator('.match-row').first()).toBeVisible();
  }
});

test('working replay survives refresh failure; explicit denial hides it until a successful retry', async ({page}) => {
  await page.goto('/manage');
  await expect(page.getByRole('button', {name:'生成工程参考赛', exact:true})).toBeEnabled();
  await page.goto('/matches/reference-chain?frame=13');
  await expect(page.getByRole('slider', {name:'回放帧'})).toHaveValue('13');
  let status = 503;
  const request = /\/api\/v1\/matches\/reference-chain$/;
  await page.route(request, route => route.fulfill({status, contentType:'application/json', body:JSON.stringify({message: status === 503 ? '本轮注入：元数据读取失败' : '本轮注入：资料封存'})}));
  const record = await page.request.post('/api/v1/sessions', {headers:{'Idempotency-Key':`state-notice-${Date.now()}`}, data:{name:'读取恢复通知检查', model:'工程检查'}});
  expect(record.status()).toBe(201);
  await expect(page.locator('.connection-banner')).toContainText('元数据读取失败');
  await expect(page.locator('canvas')).toBeVisible();
  await page.getByRole('button', {name:'下一帧 (→)', exact:true}).click();
  await expect(page.getByRole('slider', {name:'回放帧'})).toHaveValue('14');
  status = 403;
  await page.getByRole('button', {name:'重试读取', exact:true}).click();
  await expect(page.getByRole('heading', {name:'当前资料暂未开放'})).toBeVisible();
  await expect(page.locator('canvas')).toHaveCount(0);
  await pictures(page, 'viewer-denied');
  await page.unroute(request);
  await page.getByRole('button', {name:'重试读取', exact:true}).click();
  await expect(page.getByRole('slider', {name:'回放帧'})).toHaveValue('14');
});

test('workbench read retry preserves unsubmitted source and selection without page navigation', async ({page}) => {
  await page.goto('/manage');
  await page.getByLabel('参赛者名称', {exact:true}).fill(`草稿恢复 ${Date.now()}`);
  await page.getByRole('button', {name:'记录收到任务，开始 60 分钟', exact:true}).click();
  await expect(page.getByLabel('最终 bot.cpp')).toBeVisible();
  const source = '#include "arena.hpp"\n// 尚未提交的源码草稿\n';
  await page.getByLabel('最终 bot.cpp').fill(source);
  await page.getByLabel('参赛者名称', {exact:true}).fill('尚未开始的另一个记录');
  await page.getByLabel('比赛标题', {exact:true}).fill('保留比赛标题');
  await page.locator('[data-entrant-id="safe"]').getByRole('checkbox').check();
  const session = await page.getByLabel('选择收卷记录').inputValue();
  const request = /\/api\/v1\/jobs$/;
  await page.route(request, route => route.fulfill({status:503, contentType:'application/json', body:'{"message":"作业列表读取失败"}'}));
  await page.getByRole('button', {name:'刷新状态', exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('作业列表读取失败');
  await pictures(page, 'manage-draft-read-failed');
  let navigated = false;
  page.on('framenavigated', frame => { if(frame === page.mainFrame()) navigated = true; });
  await page.unroute(request);
  await page.getByRole('button', {name:'重试读取', exact:true}).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByLabel('最终 bot.cpp')).toHaveValue(source);
  await expect(page.getByLabel('参赛者名称', {exact:true})).toHaveValue('尚未开始的另一个记录');
  await expect(page.getByLabel('比赛标题', {exact:true})).toHaveValue('保留比赛标题');
  await expect(page.getByLabel('选择收卷记录')).toHaveValue(session);
  await expect(page.locator('[data-entrant-id="safe"]').getByRole('checkbox')).toBeChecked();
  expect(navigated).toBeFalsy();
});

test('workbench can retry unlocking after a transient read failure', async ({page}) => {
  const request = /\/api\/v1\/admin\/unlock$/;
  await page.route(request, route => route.fulfill({status:503, contentType:'application/json', body:'{"message":"本轮注入：本机连接失败"}'}));
  await page.goto('/manage');
  await expect(page.getByRole('alert')).toContainText('本机连接失败');
  await page.unroute(request);
  await page.getByRole('button', {name:'重试读取', exact:true}).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByRole('button', {name:'生成工程参考赛', exact:true})).toBeEnabled();
});

test('an actual empty instance has deliberate empty states and preparation links', async ({page}) => {
  const base = process.env.ARENA_EMPTY_URL;
  expect(base, 'Start a separate, new empty service instance for this case').toBeTruthy();
  for (const [name, path, title] of [['hall','/','竞技场已就绪'], ['batches','/tournaments','还没有比赛批次'], ['entrants','/entrants','还没有参赛者']]) {
    await page.goto(`${base}${path}`);
    await expect(page.getByRole('heading', {name:title, exact:true})).toBeVisible();
    await pictures(page, `${name}-empty`);
    await page.getByRole('link', {name:name === 'hall' ? /开始准备/ : '进入工作台', exact:true}).click();
    await expect(page.getByText('还没有收卷记录。先填写参赛者名称即可开始。')).toBeVisible();
    await expect(page.getByText('尚无作业。编译、单局、批次与导入会显示在这里。')).toBeVisible();
    await expect(page.getByText('最终交卷后，源码哈希、资格与编译日志在此保留。')).toBeVisible();
  }
});

test('countdown presentation never exceeds the real 60 minute deadline under client clock skew', async ({page}) => {
  // Inject only client Date.now skew; service creation/deadline stay authoritative.
  await page.addInitScript(() => { const now = Date.now; Date.now = () => now() - 5000; });
  await page.goto('/manage');
  await page.getByLabel('参赛者名称', {exact:true}).fill(`倒计时 ${Date.now()}`);
  const receipt = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/api/v1/sessions'));
  await page.getByRole('button', {name:'记录收到任务，开始 60 分钟', exact:true}).click();
  const record = await (await receipt).json();
  expect(new Date(record.deadline).getTime() - new Date(record.started_at).getTime()).toBe(3600000);
  await expect(page.locator('.session-clock strong')).toHaveText('60:00');
  await pictures(page, 'manage-countdown');
});

test('five page families share the actual design system with complete real data', async ({page}) => {
  for (const [name, path, content] of [['hall','/','.match-row'], ['viewer','/matches/reference-chain?frame=13','canvas'], ['batch','/tournaments/reference','.ranking-row'], ['entrants','/entrants','.entrant-card'], ['entrant','/entrants/heuristic','.identity-panel'], ['manage','/manage','.submission-row']]) {
    await page.goto(path);
    await expect(page.locator(content).first()).toBeVisible();
    if (name === 'hall') await expect(page.locator('.feature-board canvas')).toBeVisible();
    if (name === 'batch') await expect(page.locator('.draw-analysis')).toBeVisible();
    if (name === 'manage') await expect(page.getByRole('heading', {name:'正在读取工作台记录'})).toHaveCount(0);
    await expect(page.locator('main h1')).toHaveCount(1);
    expect(await page.locator(':root').evaluate(root => {
      const style = getComputedStyle(root);
      return ['--bg','--surface','--text','--mint'].map(key => style.getPropertyValue(key).trim().toUpperCase());
    })).toEqual(['#10151C','#1B242D','#F3F1E9','#69DCC9']);
    await pictures(page, `${name}-normal`);
  }
});
