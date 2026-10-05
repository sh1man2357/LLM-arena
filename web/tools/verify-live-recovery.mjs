/** Real service crashes, browser transport failures, and frozen-job retries. */
import { chromium, expect } from '@playwright/test';
import { spawn, execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync, existsSync, createWriteStream } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const [pythonArg, dataArg, outputArg, portArg='8797'] = process.argv.slice(2);
if (!outputArg) throw new Error('Usage: node tools/verify-live-recovery.mjs python newData output.json [port]');
const python = resolve(pythonArg), root = fileURLToPath(new URL('../..', import.meta.url)), data = resolve(dataArg), output = resolve(outputArg), base = `http://127.0.0.1:${Number(portArg)}`;
if (process.platform !== 'win32') throw new Error('This process-crash proof targets the supported Windows platform');
if (existsSync(data)) throw new Error('Use a new acceptance data directory');
mkdirSync(data, { recursive: true });
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const delay = ms => new Promise(done => setTimeout(done, ms));
let server, servicePid, boot=0, browser;
const logs = [], steps = [];
async function stopServer() {
  if (server?.pid && server.exitCode === null && server.signalCode === null) {
    process.kill(servicePid || server.pid); // Exact process owned by this proof; no /T for the crash.
    await expect.poll(() => server.exitCode !== null || server.signalCode !== null, { timeout: 10000 }).toBe(true);
  }
}
async function startServer() {
  servicePid = undefined;
  let spawnError, listening=false;
  server = spawn(python, ['-m', 'service', '--port', portArg, '--data', data], { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  const log = createWriteStream(resolve(data, `server-${++boot}.log`)); logs.push(log);
  server.stdout.pipe(log, { end: false }); server.stderr.pipe(log, { end: false });
  server.on('error', error => { spawnError=error; });
  server.stderr.on('data', bytes => { const text = bytes.toString(), match = text.match(/Started server process \[(\d+)\]/); if (match) servicePid = Number(match[1]); if (text.includes(`Uvicorn running on ${base}`)) listening=true; });
  await expect.poll(async () => {
    if (server.exitCode !== null) throw new Error(`Service exited: ${server.exitCode}`);
    if (spawnError) throw spawnError;
    if (!listening) return 'starting';
    try { return (await (await fetch(`${base}/health`)).json()).status; } catch { return 'starting'; }
  }, { timeout: 15000, intervals: [100] }).toBe('ready');
  if (!servicePid) throw new Error('Owned service PID was not observed');
}
function workerPid() {
  const bytes = execFileSync('powershell.exe', ['-NoProfile', '-Command',
    `(Get-CimInstance Win32_Process -Filter "ParentProcessId = ${servicePid}").ProcessId | ConvertTo-Json -Compress`], { windowsHide: true });
  const value = JSON.parse(bytes.toString());
  const ids = Array.isArray(value) ? value : [value];
  if (ids.length !== 1) throw new Error(`Expected one owned worker, found ${ids.length}`);
  return Number(ids[0]);
}
const alive = pid => { try { process.kill(pid, 0); return true; } catch { return false; } };
const frozenHash = identity => execFileSync(python, ['-c',
  'import sys; from service.store import Store; from engine.model import digest; print(digest(Store(sys.argv[1]).get("job",sys.argv[2])["inputs"]))', data, identity], { cwd: root, windowsHide: true }).toString().trim();
async function crashOwner() {
  const worker = workerPid(), owner = servicePid;
  await stopServer();
  await expect.poll(() => alive(worker), { timeout: 5000 }).toBe(false);
  steps.push({ owner_pid: owner, worker_pid: worker, parent_only_termination: true, worker_exited: true });
}
try {
  await startServer();
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const context = await browser.newContext({ baseURL: base });
  const api = async (path, body) => {
    const response = body === undefined ? await context.request.get(path) : await context.request.post(path, { data: body });
    if (!response.ok()) throw new Error(`${path}: ${response.status()} ${await response.text()}`);
    return response.json();
  };
  const job = id => api(`/api/v1/jobs/${id}`);
  const waitJob = async (id, status, timeout=45000) => {
    await expect.poll(async () => (await job(id)).status, { timeout, intervals: [100] }).toBe(status);
    return job(id);
  };
  const unlocked = await context.request.post('/api/v1/admin/unlock', { headers: { 'x-arena-local': '1' } });
  expect(unlocked.status()).toBe(200);
  const ids = [];
  const source = '#include "arena.hpp"\nnamespace bot { void init(uint64_t) {} Action tick(const GameState&) { return Action::WAIT; } }\n';
  for (const name of ['恢复检查 A', '恢复检查 B']) {
    const session = await api('/api/v1/sessions', { name, model: '工程检查，非真实模型生成' });
    const submitted = await api(`/api/v1/sessions/${session.id}/submit`, { source });
    const compiled = await api(`/api/v1/submissions/${submitted.id}/compile`, {});
    await waitJob(compiled.id, 'succeeded');
    ids.push((await api(`/api/v1/submissions/${submitted.id}`)).entrant_id);
  }
  console.log('Compiled two real frozen C++ submissions.');
  const control = await context.newPage(); await control.goto('/manage');
  const controlJob = id => control.locator(`[data-job-id="${id}"]`);
  const resumeFromUI = async id => {
    await controlJob(id).getByRole('button', { name: '恢复 / 重试', exact: true }).click();
  };
  const single = await api('/api/v1/matches', { entrant_ids: ids, title: '真实重启与断连', map_seed: 1, tick_interval_ms: 50 });
  const mid = single.resources.match_id, inputHash = frozenHash(single.id);
  await waitJob(single.id, 'running');
  let snapshots=0, dropped=0, duplicated=0;
  const page = await context.newPage(), errors=[];
  page.on('pageerror', error => errors.push(error.message));
  await page.route(`**/api/v1/matches/${mid}/frames*`, async route => {
    try {
    const url = new URL(route.request().url());
    const response = await route.fetch(), payload = await response.json();
    if (!url.searchParams.has('after_seq')) snapshots++;
    const activeDelta = url.searchParams.has('after_seq') && Number(url.searchParams.get('after_seq')) >= 0 && !payload.resync_required;
    if (activeDelta && payload.frames.length >= 2 && !dropped) {
      payload.frames.splice(0, 1); dropped++; await route.fulfill({ response, json: payload });
    } else if (activeDelta && payload.frames.length && dropped && !duplicated) {
      payload.frames.unshift(payload.frames[0]); duplicated++; await route.fulfill({ response, json: payload });
    } else await route.fulfill({ response });
    } catch {
      // Deliberate offline/server crashes must reach the app as network errors.
      // Do not print Playwright request diagnostics containing local cookies.
      try { await route.abort('failed'); } catch { /* page already closed */ }
    }
  });
  await page.goto(`/matches/${mid}`);
  await expect(page.locator('canvas')).toBeVisible();
  await expect.poll(() => snapshots, { timeout: 10000 }).toBeGreaterThanOrEqual(2);
  await expect.poll(() => duplicated, { timeout: 10000 }).toBe(1);
  await page.getByRole('button', { name: '初始帧 (Home)', exact: true }).click();
  for (let i=0; i<3; i++) await page.getByRole('button', { name: '下一帧 (→)', exact: true }).click();
  await page.getByLabel('播放速度').selectOption('0.25');
  const peer = await context.newPage(); await peer.goto(`/matches/${mid}`);
  await expect(peer.locator('canvas')).toBeVisible();
  const before = (await api(`/api/v1/matches/${mid}`)).ticks;
  await context.setOffline(true);
  await delay(1200);
  await expect(page.locator('canvas')).toBeVisible();
  await expect(page.getByRole('slider', { name: '回放帧' })).toHaveValue('3');
  const after = (await api(`/api/v1/matches/${mid}`)).ticks;
  expect(after).toBeGreaterThan(before);
  await context.setOffline(false);
  await expect(page.getByText('本地服务已连接', { exact: true })).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole('slider', { name: '回放帧' })).toHaveValue('3');
  await expect.poll(async () => Number(await peer.getByRole('slider', { name: '回放帧' }).inputValue()), { timeout: 5000 }).toBeGreaterThan(3);
  const slowStart = Number(await page.getByRole('slider', { name: '回放帧' }).inputValue());
  await page.getByRole('button', { name: '播放 (Space)', exact: true }).click();
  await expect.poll(async () => Number(await page.getByRole('slider', { name: '回放帧' }).inputValue()), { timeout: 3000, intervals: [100] }).toBeGreaterThan(slowStart);
  const slowEnd = Number(await page.getByRole('slider', { name: '回放帧' }).inputValue());
  expect(slowEnd-slowStart).toBeLessThanOrEqual(2);
  await page.getByLabel('播放速度').selectOption('4');
  await expect.poll(async () => Number(await page.getByRole('slider', { name: '回放帧' }).inputValue()), { timeout: 1500, intervals: [50] }).toBeGreaterThan(slowEnd+3);
  const fastEnd = Number(await page.getByRole('slider', { name: '回放帧' }).inputValue());
  await page.getByRole('button', { name: '暂停 (Space)', exact: true }).click();
  await page.getByRole('button', { name: '初始帧 (Home)', exact: true }).click();
  for (let i=0; i<3; i++) await page.getByRole('button', { name: '下一帧 (→)', exact: true }).click();
  const trace = await api(`/api/v1/matches/${mid}/frames`), firstAttempt = trace.attempt_id;
  expect(trace.partial).toBeTruthy();
  await crashOwner();
  await expect(page.locator('canvas')).toBeVisible();
  await startServer();
  const interrupted = await waitJob(single.id, 'interrupted');
  expect(interrupted.attempts[0].status).toBe('interrupted'); expect(interrupted.attempts[0].finished).toBeTruthy();
  await expect(page.getByText(/对局已中断，保留最后确认帧/)).toBeVisible({ timeout: 15000 });
  await resumeFromUI(single.id);
  const running = await waitJob(single.id, 'running');
  expect(running.attempt_id).not.toBe(firstAttempt);
  await expect(page.locator('.spectator-stage')).toHaveAttribute('data-attempt-id', running.attempt_id, { timeout: 10000 });
  await expect(page.getByRole('slider', { name: '回放帧' })).toHaveValue('0');
  const resetCount = Number(await page.locator('.spectator-stage').getAttribute('data-frame-count'));
  expect(resetCount).toBeLessThan(trace.frames.length);
  await waitJob(single.id, 'succeeded');
  const final = await api(`/api/v1/matches/${mid}/frames`);
  expect(final.frames).toHaveLength(501); expect(final.verified).toBeTruthy();
  expect(final.frames.slice(0, trace.frames.length)).toEqual(trace.frames);
  expect(frozenHash(single.id)).toBe(inputHash);
  await expect(page.locator('.spectator-stage')).toHaveAttribute('data-frame-count', '501');
  await page.getByRole('button', { name: '最后已接收帧 (End)', exact: true }).click();
  await expect(page.getByText('双方平局', { exact: true })).toBeVisible();
  console.log('Real browser gap, duplicate, offline, parent-only crash and attempt reset verified.');

  const failedSingle = await api('/api/v1/matches', { entrant_ids: ids, title: '执行进程失败与重试', map_seed: 2, tick_interval_ms: 50 });
  const failedMid = failedSingle.resources.match_id;
  await expect.poll(async () => (await api(`/api/v1/matches/${failedMid}`)).ticks, { timeout: 10000 }).toBeGreaterThan(5);
  const failingAttempt = (await job(failedSingle.id)).attempt_id;
  process.kill(workerPid());
  const failure = await waitJob(failedSingle.id, 'failed');
  expect((await api(`/api/v1/matches/${failedMid}`)).status).toBe('failed');
  const failedTrace = await api(`/api/v1/matches/${failedMid}/frames`);
  expect(failedTrace.result).toBeNull(); expect(failedTrace.verified).toBeFalsy();
  await page.goto(`/matches/${failedMid}`);
  await expect(page.getByText(/执行进程未提交完整终局；本局没有正式胜者/)).toBeVisible();
  expect(await page.getByText(/获胜$/).count()).toBe(0);
  await resumeFromUI(failedSingle.id);
  const retried = await waitJob(failedSingle.id, 'succeeded');
  expect(retried.attempts).toHaveLength(2); expect(retried.attempts[0].status).toBe('failed');
  const oldLog = await context.request.get(`/api/v1/jobs/${failedSingle.id}/log?attempt_id=${failingAttempt}`);
  expect(oldLog.status()).toBe(200);
  await controlJob(failedSingle.id).getByText('执行尝试与旧日志', { exact: true }).click();
  await expect(controlJob(failedSingle.id).getByRole('link', { name: '第 1 次日志', exact: true })).toBeVisible();
  console.log('Real worker termination preserved a failed trace and retry attempt.');

  const batch = await api('/api/v1/tournaments', { entrant_ids: ids, title: '批次边界停止与真实重启', case_count: 4, official: true });
  const tid = batch.resources.tournament_id, batchInputHash = frozenHash(batch.id);
  const rows = async () => (await api(`/api/v1/matches?tournament_id=${tid}&limit=100`)).items;
  await expect.poll(async () => (await rows()).some(m => m.status === 'running' && m.ticks > 3), { timeout: 10000 }).toBe(true);
  await controlJob(batch.id).getByRole('button', { name: '当前局后停止', exact: true }).click();
  await waitJob(batch.id, 'stopped');
  const stopped = await api(`/api/v1/tournaments/${tid}`), completed = await rows();
  expect(stopped.completed_matches).toBeGreaterThan(0); expect(stopped.completed_matches).toBeLessThan(8);
  expect(completed.every(m => m.status === 'completed' && m.verified)).toBeTruthy();
  expect(stopped.report.status).toBe('incomplete');
  expect((await context.request.post(`/api/v1/tournaments/${tid}/publish`)).status()).toBe(409);
  const cacheHashes = Object.fromEntries(completed.map(m => [m.id, m.source_sha256]));
  await resumeFromUI(batch.id);
  await expect.poll(async () => (await rows()).some(m => m.status === 'running' && m.ticks > 3), { timeout: 10000 }).toBe(true);
  await crashOwner();
  await startServer();
  await waitJob(batch.id, 'interrupted');
  expect((await api(`/api/v1/tournaments/${tid}`)).status).toBe('interrupted');
  await resumeFromUI(batch.id);
  const finished = await waitJob(batch.id, 'succeeded');
  const matches = await rows(), report = await api(`/api/v1/tournaments/${tid}/report`);
  expect(matches).toHaveLength(8); expect(new Set(matches.map(m => m.id)).size).toBe(8);
  expect(matches.every(m => m.verified && m.status === 'completed')).toBeTruthy();
  expect(report.valid_matches).toBe(8); expect(report.status).toBe('complete');
  expect(frozenHash(batch.id)).toBe(batchInputHash);
  for (const [id, hash] of Object.entries(cacheHashes)) expect(matches.find(m => m.id === id).source_sha256).toBe(hash);
  expect(finished.attempts).toHaveLength(3);
  expect(finished.attempts.map(a => a.status)).toEqual(['stopped', 'interrupted', 'succeeded']);
  expect(finished.attempts.every(a => a.finished)).toBeTruthy();
  expect(errors).toEqual([]);
  const oldTrace = resolve(data, 'jobs', single.id, firstAttempt, 'live.jsonl');
  const failedTracePath = resolve(data, 'jobs', failedSingle.id, failingAttempt, 'live.jsonl');
  const proof = { status: 'passed', platform: process.platform, browser: await browser.version(), boots: boot,
    parent_only_crashes: steps, dropped_fragments: dropped, duplicate_fragments: duplicated,
    snapshot_recovery_requests: snapshots, offline_compute_progress: { before, after }, paused_frame_preserved: 3,
    active_playback: { slow_speed: .25, slow_start: slowStart, slow_end: slowEnd, fast_speed: 4, fast_end: fastEnd },
    peer_playback_independent: true, attempt_reset_frame: 0, reset_frame_count: resetCount,
    single_job_id: single.id, frozen_single_inputs_sha256: inputHash, final_single_frames: final.frames.length,
    old_confirmed_prefix_equal: true, preserved_old_live_sha256: sha(readFileSync(oldTrace)),
    failed_job_id: failedSingle.id, old_failed_live_sha256: sha(readFileSync(failedTracePath)),
    worker_failure_without_winner: true, old_attempt_log_readable: true,
    stop_and_resume_from_browser_workbench: true,
    tournament_id: tid, frozen_batch_inputs_sha256: batchInputHash, completed_before_stop: stopped.completed_matches,
    cached_replays_unchanged: cacheHashes, batch_attempt_states: finished.attempts.map(a => a.status),
    final_matches: matches.length, valid_matches: report.valid_matches, no_duplicate_scores: true, page_errors: errors };
  writeFileSync(output, JSON.stringify(proof, null, 2));
  console.log('Boundary stop, parent-only batch crash, resume and eight unique scored matches verified.');
} finally {
  if (browser) await browser.close();
  await stopServer();
  for (const log of logs) log.end();
}
