import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  use: { baseURL: process.env.ARENA_BASE_URL || 'http://127.0.0.1:8787', browserName: 'chromium', channel: 'chrome', headless: true, trace: 'retain-on-failure' },
  reporter: [['list'], ['json', { outputFile: 'test-results/results.json' }]],
});
