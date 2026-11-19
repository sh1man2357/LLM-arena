import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('Bot 库按游戏分发任务包并复制随包提示词', async ({page, context}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto('/bots');
  for (const [game, name, file] of [
    ['bomberman', '炸弹人', 'llm-arena-devkit.zip'],
    ['gomoku', '五子棋', 'llm-arena-gomoku-devkit.zip'],
  ]) {
    await page.getByLabel('游戏', {exact: true}).selectOption(game);
    const received = page.waitForEvent('download');
    await page.getByRole('link', {name: `下载${name}任务包`}).click();
    const download = await received;
    expect(download.suggestedFilename()).toBe(file);
    expect(await readFile((await download.path())!)).toEqual(await readFile(`public/devkits/${file}`));
  }
  await page.getByRole('button', {name: '复制提示词', exact: true}).click();
  await expect(page.getByRole('button', {name: '已复制提示词'})).toBeVisible();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain('使用包内工具实际编译、练习并改进你的 Bot');
  expect(copied).toContain('单文件 bot.cpp');

  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', {value: undefined}));
  await page.getByRole('button', {name: '已复制提示词'}).click();
  await expect(page.getByRole('textbox', {name: '请手动复制提示词'})).toHaveValue(copied);
});
