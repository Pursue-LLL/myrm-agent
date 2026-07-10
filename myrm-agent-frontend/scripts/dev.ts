/**
 * [INPUT]
 * - dev-lock::acquireDevLock / assertDevLockAvailable / isDevServerHealthy (POS: dev-server lock gate)
 * - port-cleanup::APP_DEV_PORT / killListenersOnPort (POS: LISTEN-only port cleanup)
 *
 * [OUTPUT]
 * - Next.js dev server on :3000 via `bunx next dev` (webpack default)
 * - Early exit when lock+HTTP prove an existing healthy dev server
 *
 * [POS]
 * Frontend dev entry (`bun run dev`). Supervises Next.js child; writes dev-server.lock before spawn.
 */
import { type ChildProcess, execSync, spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import {
  acquireDevLock,
  assertDevLockAvailable,
  isDevServerHealthy,
  readDevLock,
  releaseDevLock,
} from './dev-lock';
import { APP_DEV_PORT, killListenersOnPort } from './port-cleanup';

const ENV_LOCAL = path.join(process.cwd(), '.env.local');
const ENV_LOCAL_HEADER = '# Auto-managed by bun run dev — local split-dev defaults\n';

function ensureDevEnvLocal(): void {
  const apiLine = 'API_PORT=8080';
  if (!fs.existsSync(ENV_LOCAL)) {
    fs.writeFileSync(
      ENV_LOCAL,
      `${ENV_LOCAL_HEADER}${apiLine}\nNEXT_PUBLIC_DEPLOY_MODE=local\n`,
      'utf8',
    );
    console.log(`📝 Created ${ENV_LOCAL} with ${apiLine}`);
    return;
  }
  const content = fs.readFileSync(ENV_LOCAL, 'utf8');
  if (!/\bAPI_PORT\s*=/.test(content)) {
    fs.appendFileSync(ENV_LOCAL, `\n${apiLine}\n`, 'utf8');
    console.log(`📝 Appended ${apiLine} to ${ENV_LOCAL}`);
  }
}

const args = process.argv.slice(2);
const clean = args.includes('--clean');

ensureDevEnvLocal();

if (clean) {
  console.log('🧹 Cleaning .next directory...');
  fs.rmSync('.next', { recursive: true, force: true });
}

function isFrontendHttpOk(): boolean {
  try {
    execSync(`curl -sf --max-time 3 http://127.0.0.1:${APP_DEV_PORT}/`, { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function setupSignalHandlers(child: ChildProcess) {
  const signals: NodeJS.Signals[] = ['SIGINT', 'SIGTERM', 'SIGHUP'];

  signals.forEach((signal) => {
    process.on(signal, () => {
      console.log(`\n🛑 Received ${signal}, terminating Next.js on :${APP_DEV_PORT}...`);
      try {
        child.kill('SIGTERM');
      } catch {
        // ignore
      }
      setTimeout(() => {
        killListenersOnPort(APP_DEV_PORT, true);
        releaseDevLock();
        process.exit(0);
      }, 1000);
    });
  });
}

if (isDevServerHealthy(APP_DEV_PORT) && isFrontendHttpOk()) {
  const lock = readDevLock();
  console.log(
    `✅ Dev server already healthy → http://127.0.0.1:${APP_DEV_PORT} (PID ${lock?.pid ?? 'unknown'})`,
  );
  process.exit(0);
}

assertDevLockAvailable(APP_DEV_PORT);
console.log(`🧹 Freeing port ${APP_DEV_PORT} (myrm-agent-frontend only)...`);
killListenersOnPort(APP_DEV_PORT);
acquireDevLock(APP_DEV_PORT);

const bindLan =
  process.env.WEBUI_DEV_BIND_ALL === '1' || process.env.WEBUI_DEV_BIND_ALL === 'true' || args.includes('--lan');
const nextArgs = ['next', 'dev', '-p', String(APP_DEV_PORT)];
// Turbopack needs native @next/swc-darwin-arm64; WASM-only installs fail on darwin/arm64.
if (!args.includes('--turbo')) {
  nextArgs.push('--webpack');
}
if (bindLan) {
  nextArgs.push('-H', '0.0.0.0');
  console.log(`🌐 LAN bind enabled (0.0.0.0:${APP_DEV_PORT}) — use intranet IP from Settings → System`);
}

console.log(`🚀 Starting Next.js on port ${APP_DEV_PORT}...`);
const child = spawn('bunx', [...nextArgs], {
  stdio: 'inherit',
  detached: false,
});

setupSignalHandlers(child);

child.on('exit', (code) => {
  console.log('🏁 Next.js exited with code:', code);
  killListenersOnPort(APP_DEV_PORT, true);
  releaseDevLock();
  process.exit(code ?? 0);
});

child.on('error', (err) => {
  console.error('❌ Failed to start Next.js:', err);
  killListenersOnPort(APP_DEV_PORT, true);
  releaseDevLock();
  process.exit(1);
});
