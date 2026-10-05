import { defineConfig } from '@playwright/test';

const baseURL = process.env.ARENA_BASE_URL;
if (!baseURL) {
  throw new Error('Set ARENA_BASE_URL to a dedicated test instance before running browser tests. Workflow tests create submissions and tournaments; use a data directory under artifacts/work.');
}

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  // Workflow tests share a persistent service with one FIFO compute worker.
  // Run them in order so an unrelated archive job cannot consume a live window.
  workers: 1,
  use: { baseURL, browserName: 'chromium', channel: 'chrome', headless: true, trace: 'retain-on-failure' },
  reporter: [['list'], ['json', { outputFile: process.env.ARENA_BROWSER_RESULTS || 'test-results/results.json' }]],
});
