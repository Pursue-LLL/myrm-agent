import { defineConfig } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  webServer: process.env.PLAYWRIGHT_SKIP_WEBSERVER
    ? undefined
    : [
        {
          command: 'NEXT_PUBLIC_DEPLOY_MODE=local bun run dev',
          url: baseURL,
          reuseExistingServer: !process.env.PLAYWRIGHT_FORCE_WEBSERVER,
          timeout: 120_000,
        },
      ],
});
