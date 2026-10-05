/** Actual readable viewport evidence; review conclusions are recorded separately. */
import { chromium, expect } from '@playwright/test';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';

const [base = 'http://127.0.0.1:8863', out = '../artifacts/acceptance/v0.2-development/final'] = process.argv.slice(2);
const output = resolve(out), visual = resolve(output, 'visual/review-viewport');
mkdirSync(visual, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome' });
const context = await browser.newContext({ baseURL: base });
const page = await context.newPage(), screenshots = [], errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  const response = await context.request.get('/api/v1/matches?entrant=heuristic&tournament_id=reference-v01&limit=1');
  expect(response.ok()).toBeTruthy();
  const match = (await response.json()).items[0].id;
  const entrants = await context.request.get('/api/v1/entrants'); expect(entrants.ok()).toBeTruthy();
  const longName = (await entrants.json()).items.find(e => e.id === 'heuristic').name;
  for (const width of [390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const [name, path, selector] of [
      ['hall', '/', '.feature-match canvas'], ['viewer', `/matches/${match}?frame=0`, 'canvas'],
      ['batch', '/tournaments/reference-v01', '.ranking-row'], ['entrants', '/entrants', '.entrant-card'],
      ['profile', '/entrants/heuristic', '.match-row'], ['manage', '/manage', '.workflow-grid input'],
    ]) {
      await page.goto(path); await expect(page.locator(selector).first()).toBeVisible();
      await expect(page.getByText('本地服务已连接', { exact: true })).toBeVisible();
      const identitySelector = { viewer: '.versus-player', batch: '.ranking-row', entrants: '.entrant-card', profile: '.match-row', manage: '[data-entrant-id="heuristic"]' }[name];
      if (identitySelector) await expect(page.locator(identitySelector).filter({ hasText: longName }).first()).toBeVisible();
      if (name === 'viewer') await expect(page.getByRole('slider', { name: '回放帧' })).toHaveValue('0');
      if (name === 'manage') await expect(page.getByRole('heading', { name: '正在读取工作台记录' })).toHaveCount(0);
      await page.evaluate(() => document.fonts.ready);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      const file = `${name}-${width}.png`; await page.screenshot({ path: resolve(visual, file) });
      screenshots.push({ file, path, width, height: 1000, sha256: createHash('sha256').update(readFileSync(resolve(visual, file))).digest('hex') });
    }
  }
  expect(errors).toEqual([]);
  writeFileSync(resolve(output, 'checks/review-viewport.json'), JSON.stringify({ status: 'captured', screenshots, page_errors: errors, human_approval: false }, null, 2) + '\n');
  console.log(`Captured ${screenshots.length} actual viewports. Human approval is recorded separately.`);
} finally { await context.close(); await browser.close(); }
