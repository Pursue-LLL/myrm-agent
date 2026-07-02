import { defineConfig } from '@playwright/test';
import { existsSync } from 'node:fs';

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000';
const chromePath =
  process.env.PLAYWRIGHT_CHROME_EXECUTABLE_PATH?.trim() ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const launchOptions = existsSync(chromePath) ? { executablePath: chromePath } : undefined;

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL,
    trace: 'on-first-retry',
    // Next.js dev keeps HMR sockets open — never wait for full "load".
    navigationTimeout: 15_000,
    actionTimeout: 10_000,
    ...(launchOptions ? { launchOptions } : {}),
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
