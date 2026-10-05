import { test, expect } from '@playwright/test';

test('real chained-explosion replay supports exact seeking, events, keyboard and export', async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto('/matches/reference-chain');
  await expect(page.getByText('世界回放已验证')).toBeVisible();
  await page.getByRole('button', { name: '下一帧 (→)', exact: true }).click();
  await expect(page.getByRole('slider', { name: '回放帧' })).toHaveValue('1');
  await page.locator('body').click({ position: {x: 5, y: 5} });
  await page.keyboard.press('End');
  await expect(page.getByRole('slider', { name: '回放帧' })).toHaveValue('19');
  await expect(page.getByText('双方平局', { exact: true })).toBeVisible();
  await expect(page.locator('.versus-player').getByText(/淘汰于 Tick 18/)).toHaveCount(2);
  await page.getByRole('button', { name: '初始帧 (Home)', exact: true }).click();
  await page.getByRole('button', { name: /爆炸.*炸弹 #/ }).first().click();
  await expect(page.getByRole('slider', { name: '回放帧' })).toHaveValue('19');
  await page.getByLabel('播放速度').selectOption('4');
  await page.getByLabel('当前事件叠层').uncheck();
  await page.getByRole('button', { name: '格子', exact: true }).click();
  await page.getByLabel('格子 x').fill('4');
  await page.getByLabel('格子 y').fill('4');
  await expect(page.getByText('硬墙', { exact: true })).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'PNG', exact: true }).click();
  expect((await download).suggestedFilename()).toContain('frame-19.png');
  await page.reload();
  await expect(page.getByRole('slider', { name: '回放帧' })).toHaveValue('19');
  expect(errors).toEqual([]);
});

test('batch report uses authoritative scores, pair selection and map swap cases', async ({ page }) => {
  await page.goto('/tournaments/reference-v01');
  await expect(page.getByRole('heading', { name: '批次榜单' })).toBeVisible();
  await expect(page.locator('.ranking-row')).toHaveCount(3);
  await page.locator('.matrix-cell').filter({ hasText: '0.47' }).click();
  await expect(page.getByText('0.470', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '地图案例 1，均分 0.5', exact: true }).click();
  await expect(page.locator('.match-row')).toHaveCount(2);
  await page.locator('.match-row').first().click();
  await expect(page.getByRole('link', { name: '同地图换边局' })).toBeVisible();
});

test('responsive high-fidelity pages use real data without horizontal overflow', async ({ page }) => {
  for (const width of [390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const [name, path] of [['hall', '/'], ['viewer', '/matches/reference-chain?frame=16'], ['batch', '/tournaments/reference-v01'], ['manage', '/manage']]) {
      await page.goto(path);
      if (name === 'viewer') await expect(page.getByRole('slider', { name: '回放帧' })).toHaveValue('16');
      else await expect(page.locator('h1')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
      if (name === 'viewer') {
        const size = await page.locator('canvas').boundingBox();
        expect(Math.abs(size!.width / size!.height - 13 / 11)).toBeLessThan(.01);
      }
      await page.screenshot({ path: `../artifacts/acceptance/v0.2-development/visual/${name}-${width}.png`, fullPage: true });
    }
  }
});
