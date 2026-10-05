import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  // Workflow tests share a persistent service with one FIFO compute worker.
  // Run them in order so an unrelated archive job cannot consume a live window.
  workers: 1,
  use: { baseURL: process.env.ARENA_BASE_URL || 'http://127.0.0.1:8787', browserName: 'chromium', channel: 'chrome', headless: true, trace: 'retain-on-failure' },
  reporter: [['list'], ['json', { outputFile: process.env.ARENA_BROWSER_RESULTS || 'test-results/results.json' }]],
});
