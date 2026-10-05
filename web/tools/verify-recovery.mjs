import { chromium, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const [base, sourceBase, proofPath, sourceData, output] = process.argv.slice(2);
if (!output) throw new Error('Usage: node tools/verify-recovery.mjs restoredURL sourceURL recovery.json sourceData output.json');
const proof = JSON.parse(readFileSync(proofPath, 'utf8'));
if (!proof.workflow) throw new Error('Missing restored end-to-end workflow');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  const stale = await browser.newContext();
  await stale.addCookies([{ name: 'arena_owner', value: readFileSync(`${sourceData}/owner.token`, 'utf8'), url: base }]);
  expect((await stale.request.get(`${base}/api/v1/submissions`)).status()).toBe(403);
  await stale.close();
  const context = await browser.newContext({ baseURL: base, permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await context.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(`/matches/${proof.public_replay_id}?frame=19`);
  await expect(page.getByText(/公开副本：已重算世界轨迹/)).toBeVisible();
  await expect(page.getByRole('slider', { name: '回放帧' })).toHaveValue('19');
  await expect(page.getByText('淘汰于 Tick 18')).toHaveCount(2);
  await page.getByRole('button', { name: '复制帧链接', exact: true }).click();
  await expect(page.getByText('已复制本地对局与帧链接。', { exact: true })).toBeVisible();
  const link = await page.evaluate(() => navigator.clipboard.readText());
  expect(new URL(link).searchParams.get('frame')).toBe('19');
  expect(new URL(link).pathname).toBe(`/matches/${proof.public_replay_id}`);
  await page.goto(link);
  await expect(page.getByRole('slider', { name: '回放帧' })).toHaveValue('19');
  const replayDownload = page.waitForEvent('download');
  await page.getByRole('link', { name: '公开 Replay', exact: true }).click();
  const replay = JSON.parse(readFileSync((await (await replayDownload).path()), 'utf8'));
  expect(replay.verified).toBeTruthy();
  expect(replay.bot_rerunnable).toBeFalsy();
  const pngDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'PNG', exact: true }).click();
  const png = readFileSync((await (await pngDownload).path()));
  expect(png.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
  const workflow = proof.workflow;
  await page.goto(`/matches/${workflow.match_id}?frame=500`);
  await expect(page.getByText('世界回放已验证', { exact: true })).toBeVisible();
  await expect(page.getByRole('slider', { name: '回放帧' })).toHaveValue('500');
  await expect(page.getByText('双方平局', { exact: true })).toBeVisible();
  await page.goto(`/tournaments/${workflow.tournament_id}`);
  await expect(page.locator('.ranking-row')).toHaveCount(2);
  await expect(page.locator('.match-row')).toHaveCount(2);
  const reportDownload = page.waitForEvent('download');
  await page.getByRole('link', { name: '导出报告', exact: true }).click();
  const reportBytes = readFileSync(await (await reportDownload).path());
  const previousReport = await context.request.get(`${sourceBase}/api/v1/exports/${workflow.tournament_id}?kind=report`);
  expect(sha(reportBytes)).toBe(sha(await previousReport.body()));
  const manifestResponse = await context.request.get(`/api/v1/exports/${workflow.tournament_id}?kind=publication`);
  expect(sha(await manifestResponse.body())).toBe(workflow.publication_sha256);
  const unlock = page.waitForResponse(r => r.url().endsWith('/api/v1/admin/unlock') && r.request().method() === 'POST');
  await page.goto('/manage');
  expect((await unlock).status()).toBe(200);
  const submissionsResponse = await context.request.get('/api/v1/submissions');
  expect(submissionsResponse.status()).toBe(200);
  const submissions = (await submissionsResponse.json()).items;
  const submitted = submissions.find(s => s.id === workflow.submission_id);
  expect(submitted.status).toBe('qualified');
  expect(submitted.source_sha256).toBe(workflow.source_sha256);
  expect(submitted.wasm_sha256).toBe(workflow.wasm_sha256);
  const frozen = page.locator('.submission-row').filter({ hasText: submitted.name });
  await expect(frozen.getByText('资格通过', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '备份与新目录恢复', exact: true })).toBeVisible();
  expect(errors).toEqual([]);
  writeFileSync(output, JSON.stringify({ status: 'passed', browser: await browser.version(),
    archive_sha256: proof.archive_sha256, workflow, old_credentials_rejected: true,
    public_replay_id: proof.public_replay_id, exact_frame_link: true, png_signature_verified: true,
    restored_public_replay_download: true, restored_report_sha256: sha(reportBytes),
    publication_hash_unchanged: true, frozen_source_and_wasm_unchanged: true, page_errors: errors }, null, 2));
  console.log('Restored Chrome workflow, credentials, frame clipboard, PNG and immutable downloads verified.');
} finally {
  await browser.close();
}
