import { defineConfig } from '@playwright/test';

const baseURL = process.env.ARENA_BASE_URL;
if (!baseURL) {
  throw new Error('Set ARENA_BASE_URL to a dedicated test instance with data under artifacts/work. Tests create Bots and single runs.');
}

export default defineConfig({
  testDir: './tests',
  timeout: 60000,
  // Tests share one dedicated instance with one compute slot.
  workers: 1,
  use: { baseURL, browserName: 'chromium', channel: 'chrome', headless: true, trace: 'retain-on-failure' },
  reporter: [['list'], ['json', { outputFile: process.env.ARENA_BROWSER_RESULTS || 'test-results/results.json' }]],
});
