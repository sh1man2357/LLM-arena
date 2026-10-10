import { test, expect, type Page } from '@playwright/test';
import type { Frame, Match, Replay } from '../src/types';

// Model independent compute and playback clocks: each read can append a whole batch.
async function recording(page: Page, count: number, completed = false) {
  const time = new Date('2026-10-11T00:00:00Z');
  await page.clock.install({time});
  await page.clock.pauseAt(time);
  const stream = {count, completed};
  const entrants = [0, 1].map(slot => ({id: `bot-${slot}`, name: `Bot ${slot}`, slot, wasm_sha256: 'test'}));
  const frame = (seq: number): Frame => ({seq, tick: seq ? seq - 1 : null,
    state: {tick: seq, grid: Array(143).fill(0), bombs: [],
      players: entrants.map(e => ({id: e.slot, x: e.slot ? 11 : 1, y: e.slot ? 9 : 1, alive: true, death_tick: null})),
      fault_counters: entrants.map(() => ({consecutive: 0, total: 0}))},
    calls: [], actions: [], events: [], visual: {coverage: [], exploded_bombs: [], blocked_moves: []}});
  const result = () => stream.completed ? {valid: true, ticks: stream.count - 1, reason: 'tick_limit',
    groups: [[0, 1]], players: entrants.map(e => ({id: e.slot, placement_score: .5}))} : null;
  const match = (): Match => ({id: 'playback-test', title: '缓冲播放测试', status: stream.completed ? 'completed' : 'running',
    entrants, ticks: stream.count - 1, verified: stream.completed, result: result(), created: time.toISOString(), map_seed: 1});
  await page.route('**/api/v1/status', route => route.fulfill({json: {busy: false}}));
  await page.route('**/api/v1/matches/playback-test', route => route.fulfill({json: match()}));
  await page.route('**/api/v1/matches/playback-test/frames**', route => {
    const after = Number(new URL(route.request().url()).searchParams.get('after_seq') ?? -1);
    const replay: Replay = {attempt_id: 'playback-test', width: 13, height: 11, entrants, initialization: [], rules: {},
      partial: !stream.completed, verified: stream.completed, result: result(), last_seq: stream.count - 1,
      frames: Array.from({length: stream.count}, (_, seq) => frame(seq)).filter(f => f.seq > after)};
    return route.fulfill({json: replay});
  });
  return {stream, match};
}

test('批量到帧与后台结束不跳 Tick，慢速、暂停和末尾结果独立', async ({page}) => {
  const {stream} = await recording(page, 4);
  await page.goto('/matches/playback-test');
  const stage = page.locator('.spectator-stage');
  await expect(stage).toHaveAttribute('data-seq', '0');
  await expect(page.getByRole('button', {name: '暂停', exact: true})).toBeVisible();
  await page.getByLabel('倍速', {exact: true}).selectOption('0.25');
  stream.count = 9;
  await page.clock.runFor(400);
  await expect(stage).toHaveAttribute('data-frame-count', '9');
  await expect(stage).toHaveAttribute('data-seq', '0');
  await page.clock.runFor(600);
  await expect(stage).toHaveAttribute('data-seq', '1');
  await page.getByRole('button', {name: '暂停', exact: true}).click();
  stream.count = 13;
  await page.clock.runFor(1200);
  await expect(stage).toHaveAttribute('data-frame-count', '13');
  await expect(stage).toHaveAttribute('data-seq', '1');
  stream.completed = true;
  await page.clock.runFor(3000);
  await expect(page.locator('.badge')).toHaveText('已结束');
  await expect(stage).toHaveAttribute('data-seq', '1');
  await expect(page.getByRole('heading', {name: '平局', exact: true})).toBeHidden();
  await page.getByLabel('倍速', {exact: true}).selectOption('4');
  await page.getByRole('button', {name: '播放', exact: true}).click();
  for (let seq = 2; seq < 13; seq++) {
    await page.clock.runFor(63);
    await expect(stage).toHaveAttribute('data-seq', String(seq));
  }
  await expect(page.getByRole('button', {name: '播放', exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: '平局', exact: true})).toBeVisible();
  await page.reload();
  await expect(stage).toHaveAttribute('data-seq', '0');
  await expect(page.getByRole('button', {name: '播放', exact: true})).toBeVisible();
});

test('播完缓冲自动等待和续播，回到最新只跳转一次', async ({page}) => {
  const {stream} = await recording(page, 1);
  await page.goto('/matches/playback-test');
  const stage = page.locator('.spectator-stage');
  await expect(page.getByText('等待下一帧…', {exact: true})).toBeVisible();
  await page.clock.runFor(1000);
  await expect(stage).toHaveAttribute('data-seq', '0');
  stream.count = 4;
  await page.clock.runFor(400);
  await expect(stage).toHaveAttribute('data-frame-count', '4');
  await expect(stage).toHaveAttribute('data-seq', '0');
  for (let seq = 1; seq < 4; seq++) {
    await page.clock.runFor(250);
    await expect(stage).toHaveAttribute('data-seq', String(seq));
  }
  await expect(page.getByText('等待下一帧…', {exact: true})).toBeVisible();
  await page.getByRole('button', {name: '回到初始帧'}).click();
  stream.count = 7;
  await page.clock.runFor(400);
  await expect(stage).toHaveAttribute('data-frame-count', '7');
  await expect(stage).toHaveAttribute('data-seq', '0');
  await page.getByRole('button', {name: '回到最新'}).click();
  await expect(stage).toHaveAttribute('data-seq', '6');
  stream.count = 10;
  await page.clock.runFor(400);
  await expect(stage).toHaveAttribute('data-frame-count', '10');
  await expect(stage).toHaveAttribute('data-seq', '6');
  for (let seq = 7; seq < 10; seq++) {
    await page.clock.runFor(250);
    await expect(stage).toHaveAttribute('data-seq', String(seq));
  }
  await expect(page.getByText('等待下一帧…', {exact: true})).toBeVisible();
});

test('新建的快速终局也从头自动播放，刷新历史录像则暂停', async ({page}) => {
  const {match} = await recording(page, 4, true);
  await page.route('**/api/v1/bots', route => route.fulfill({json: {items: [
    {id: 'bot-0', name: 'Bot 0', status: 'ready', baseline: true, created: ''},
  ]}}));
  await page.route('**/api/v1/matches?*', route => route.fulfill({json: {items: [], total: 0}}));
  await page.route('**/api/v1/matches', route => route.fulfill({status: 202, json: match()}));
  await page.goto('/');
  await page.getByRole('button', {name: '开始对战', exact: true}).click();
  const stage = page.locator('.spectator-stage');
  await expect(stage).toHaveAttribute('data-seq', '0');
  await expect(page.getByRole('button', {name: '暂停', exact: true})).toBeVisible();
  await page.clock.runFor(250);
  await expect(stage).toHaveAttribute('data-seq', '1');
  await page.reload();
  await expect(stage).toHaveAttribute('data-seq', '0');
  await expect(page.getByRole('button', {name: '播放', exact: true})).toBeVisible();
});
