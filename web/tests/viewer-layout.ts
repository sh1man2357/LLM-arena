import { expect, type Page } from '@playwright/test';

export async function checkPlayerLayout(page: Page, aspectRatio: number) {
  for (const viewport of [{width: 1024, height: 768}, {width: 844, height: 390}, {width: 390, height: 844}]) {
    await page.setViewportSize(viewport);
    await page.evaluate(() => window.scrollTo(0, 0));
    const board = page.locator('.spectator-stage canvas');
    const controls = page.locator('.controls');
    await expect(board).toBeInViewport({ratio: 1});
    await expect(controls).toBeInViewport({ratio: 1});

    const canvas = (await board.boundingBox())!;
    const panel = (await page.locator('.playback').boundingBox())!;
    expect(canvas.height).toBeGreaterThan(100);
    expect(Math.abs(canvas.width - canvas.height * aspectRatio)).toBeLessThan(1);
    expect(canvas.y + canvas.height <= panel.y + 1 || canvas.x + canvas.width <= panel.x + 1).toBe(true);
  }
}
