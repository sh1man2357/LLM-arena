import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';

const sha = (data: Buffer) => createHash('sha256').update(data).digest('hex');

// Repeated suites must import a fresh archive, while preserving every original
// entry byte. A ZIP comment changes only container identity, not frozen evidence.
function withComment(original: Buffer, comment: string) {
  const offset = original.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  if (offset < 0 || offset + 22 + original.readUInt16LE(offset + 20) !== original.length) throw new Error('Invalid ZIP end record');
  const end = Buffer.from(original.subarray(0, offset + 22)), bytes = Buffer.from(comment, 'utf8');
  if (bytes.length > 65535) throw new Error('ZIP comment too large');
  end.writeUInt16LE(bytes.length, offset + 20);
  return Buffer.concat([end, bytes]);
}

test('host imports full legacy archive, compares swaps and downloads immutable publication', async ({ page }) => {
  test.setTimeout(120000);
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  const path = resolve('../artifacts/acceptance/v0.1-release/evidence.zip');
  const original = readFileSync(path), originalHash = sha(original);
  const title = `浏览器旧证据 ${Date.now()}`;
  const data = withComment(original, title);
  await page.goto('/manage');
  const receipt = page.waitForResponse(r => r.url().includes('/api/v1/imports/archive') && r.request().method() === 'POST');
  await page.getByLabel('上传批次 ZIP', { exact: true }).setInputFiles({ name: `${title}.zip`, mimeType: 'application/zip', buffer: data });
  const response = await receipt; expect(response.status()).toBe(202);
  const job = await response.json();
  await expect(page.locator(`[data-job-id="${job.id}"] .job-info > .record-heading`).getByText('已完成', { exact: true })).toBeVisible({ timeout: 60000 });
  const publication = page.locator('.publication-row').filter({ hasText: title });
  await publication.getByRole('link', { name: title, exact: true }).click();
  await expect(page.getByText(new RegExp('历史证据导入'))).toBeVisible();
  await expect(page.locator('.ranking-row')).toHaveCount(3);
  await page.locator('.matrix-cell').filter({ hasText: '0.47' }).click();
  await expect(page.getByText('0.470', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '地图案例 1，均分 0.5', exact: true }).click();
  await expect(page.locator('.match-row')).toHaveCount(2);
  await page.locator('.match-row').first().click();
  await expect(page.getByText('世界回放已验证', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: '同地图换边局' })).toBeVisible();
  const matchId = new URL(page.url()).pathname.split('/').pop()!;
  const publicViewer = await page.context().browser()!.newContext();
  expect((await publicViewer.request.get(new URL(`/api/v1/matches/${matchId}/frames`, page.url()).href)).status()).toBe(403);
  expect((await publicViewer.request.get(new URL(`/api/v1/tournaments/${job.resources.tournament_id}`, page.url()).href)).status()).toBe(403);
  await publicViewer.close();
  expect((await page.request.post(`/api/v1/tournaments/${job.resources.tournament_id}/publish`)).status()).toBe(409);
  await page.goto('/manage');
  await publication.getByRole('button', { name: '确认原收卷结束并开放观看', exact: true }).click();
  await publication.getByRole('button', { name: '校验并发布成绩', exact: true }).click();
  await expect(publication.getByRole('link', { name: '下载发布清单', exact: true })).toBeVisible({ timeout: 60000 });
  const downloadEvent = page.waitForEvent('download');
  await publication.getByRole('link', { name: '下载发布清单', exact: true }).click();
  const download = await downloadEvent;
  const manifest = JSON.parse(readFileSync((await download.path())!, 'utf-8'));
  expect(manifest.matches).toHaveLength(300);
  expect(manifest.disclosure).toBe('archived');
  const replay = await page.request.get(`/api/v1/exports/${matchId}`);
  expect(replay.ok()).toBeTruthy();
  const source = manifest.matches.find((row: {id: string}) => row.id === matchId);
  expect(sha(await replay.body())).toBe(source.public_sha256);
  expect((await replay.json()).source_sha256).toBe(source.source_sha256);
  const report = await page.request.get(`/api/v1/exports/${job.resources.tournament_id}?kind=report`);
  expect(sha(await report.body())).toBe(manifest.report.public_sha256);
  const printed = JSON.stringify(manifest) + await replay.text();
  for (const forbidden of ['map_seed', 'bot_seeds', 'source_files', 'C:\\Users', 'diagnostic']) expect(printed).not.toContain(forbidden);
  const publishedBefore = await (await page.request.get(`/api/v1/tournaments/${job.resources.tournament_id}`)).json();
  const firstKey = (await response.request().allHeaders())['idempotency-key'];expect(firstKey).toBeTruthy();
  const repeatImport = await page.request.post(response.url(), {headers:{'idempotency-key':firstKey},multipart:{file:{name:`${title}.zip`,mimeType:'application/zip',buffer:data}}});
  expect(repeatImport.status()).toBe(202);expect((await repeatImport.json()).id).toBe(job.id);
  const publishedAfter = await (await page.request.get(`/api/v1/tournaments/${job.resources.tournament_id}`)).json();
  expect(publishedAfter.disclosure).toBe('archived');expect(publishedAfter.publication_id).toBe(publishedBefore.publication_id);
  expect(sha(readFileSync(path))).toBe(originalHash);
  expect(errors).toEqual([]);
});

test('bad archive produces an actionable failed job and no batch', async ({ page }) => {
  await page.goto('/manage');
  const receipt = page.waitForResponse(r => r.url().includes('/api/v1/imports/archive') && r.request().method() === 'POST');
  await page.getByLabel('上传批次 ZIP', { exact: true }).setInputFiles({ name: '损坏的归档.zip', mimeType: 'application/zip', buffer: Buffer.from('invalid ZIP') });
  const job = await (await receipt).json();
  const row = page.locator(`[data-job-id="${job.id}"]`);
  await expect(row.locator('.job-info > .record-heading').getByText('运行失败', { exact: true })).toBeVisible({ timeout: 10000 });
  await expect(row.getByText(/Archive cannot be read/)).toBeVisible();
  await expect(row.getByRole('button', { name: '恢复 / 重试', exact: true })).toBeVisible();
  await expect(row.getByRole('link', { name: '执行日志', exact: true })).toBeVisible();
  expect((await page.request.get(`/api/v1/tournaments/${job.resources.tournament_id}`)).status()).toBe(404);
});
