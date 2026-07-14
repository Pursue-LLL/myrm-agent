/**
 * [INPUT]
 * - dev-lock::tryAttachToHealthyDevServer / acquireDevLock (POS: dev-server lock gate)
 * - port-cleanup::APP_DEV_PORT / killListenersOnPort (POS: LISTEN-only port cleanup)
 *
 * [OUTPUT]
 * - Next.js dev server on :3000 via `bunx next dev` (Turbopack default when native SWC present)
 * - Early exit when lock+HTTP prove an existing healthy dev server
 *
 * [POS]
 * Frontend dev entry (`bun run dev` / `dev:lan` / `dev:clean`). Runs locale namespace split, supervises Next.js child.
 */
import { type ChildProcess, spawn, spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import {
  acquireDevLock,
  assertDevLockAvailable,
  readDevLock,
  releaseDevLock,
  tryAttachToHealthyDevServer,
} from './dev-lock';
import { APP_DEV_PORT, killListenersOnPort } from './port-cleanup';

const ENV_LOCAL = path.join(process.cwd(), '.env.local');
const ENV_LOCAL_HEADER = '# Auto-managed by bun run dev — local split-dev defaults\n';

const SPLIT_LOCALE_SCRIPT = path.join(__dirname, 'split-locale-namespaces.mjs');

function ensureLocaleNamespaces(): void {
  const result = spawnSync(process.execPath, [SPLIT_LOCALE_SCRIPT], {
    cwd: path.join(__dirname, '..'),
    stdio: 'inherit',
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function ensureDevEnvLocal(): void {
  const apiPort = process.env.API_PORT?.trim() || '8080';
  const apiLine = `API_PORT=${apiPort}`;
  if (!fs.existsSync(ENV_LOCAL)) {
    fs.writeFileSync(ENV_LOCAL, `${ENV_LOCAL_HEADER}${apiLine}\nNEXT_PUBLIC_DEPLOY_MODE=local\n`, 'utf8');
    console.log(`📝 Created ${ENV_LOCAL} with ${apiLine}`);
    return;
  }
  const content = fs.readFileSync(ENV_LOCAL, 'utf8');
  if (content.startsWith(ENV_LOCAL_HEADER)) {
    const updated = content.replace(/^API_PORT\s*=.*$/m, apiLine);
    if (updated !== content) {
      fs.writeFileSync(ENV_LOCAL, updated, 'utf8');
      console.log(`📝 Updated ${ENV_LOCAL} with ${apiLine}`);
    }
    return;
  }
  if (!/\bAPI_PORT\s*=/.test(content)) {
    fs.appendFileSync(ENV_LOCAL, `\n${apiLine}\n`, 'utf8');
    console.log(`📝 Appended ${apiLine} to ${ENV_LOCAL}`);
  }
}

const args = process.argv.slice(2);
const clean = args.includes('--clean');

ensureLocaleNamespaces();
ensureDevEnvLocal();

if (clean) {
  console.log('🧹 Cleaning .next directory...');
  fs.rmSync('.next', { recursive: true, force: true });
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

if (tryAttachToHealthyDevServer(APP_DEV_PORT)) {
  const lock = readDevLock();
  console.log(`✅ Dev server already healthy → http://127.0.0.1:${APP_DEV_PORT} (PID ${lock?.pid ?? 'unknown'})`);
  process.exit(0);
}

assertDevLockAvailable(APP_DEV_PORT);

if (tryAttachToHealthyDevServer(APP_DEV_PORT)) {
  const lock = readDevLock();
  console.log(
    `✅ Dev server attached after lock reconcile → http://127.0.0.1:${APP_DEV_PORT} (PID ${lock?.pid ?? 'unknown'})`,
  );
  process.exit(0);
}

console.log(`🧹 Freeing port ${APP_DEV_PORT} (myrm-agent-frontend only)...`);
killListenersOnPort(APP_DEV_PORT);
acquireDevLock(APP_DEV_PORT);

const bindLan =
  process.env.WEBUI_DEV_BIND_ALL === '1' || process.env.WEBUI_DEV_BIND_ALL === 'true' || args.includes('--lan');
const nextArgs = ['next', 'dev', '-p', String(APP_DEV_PORT)];

function nativeSwcPackage(): string | null {
  const platform = `${process.platform}-${process.arch}`;
  const map: Record<string, string> = {
    'darwin-arm64': '@next/swc-darwin-arm64',
    'darwin-x64': '@next/swc-darwin-x64',
    'linux-arm64': '@next/swc-linux-arm64-gnu',
    'linux-x64': '@next/swc-linux-x64-gnu',
  };
  const pkg = map[platform];
  if (!pkg) return null;
  const pkgDir = path.join(process.cwd(), 'node_modules', pkg);
  return fs.existsSync(pkgDir) ? pkg : null;
}

const forceWebpack = args.includes('--webpack');
const bundlerMode = forceWebpack ? 'webpack' : 'turbopack';
const BUNDLER_STAMP = path.join('.next', 'dev-bundler-mode');

function ensureBundlerCacheCoherent(mode: string): void {
  if (clean) {
    return;
  }
  try {
    if (fs.existsSync(BUNDLER_STAMP)) {
      const previous = fs.readFileSync(BUNDLER_STAMP, 'utf8').trim();
      if (previous && previous !== mode) {
        console.log(`🧹 Dev bundler changed (${previous} → ${mode}) — clearing .next cache...`);
        fs.rmSync('.next', { recursive: true, force: true });
      }
    }
  } catch (error) {
    console.warn('⚠️  Could not validate dev bundler cache:', error);
  }
}

if (forceWebpack) {
  nextArgs.push('--webpack');
} else if (!nativeSwcPackage()) {
  console.error('❌ Native @next/swc is missing — dev compile will be extremely slow.');
  console.error('   Run: cd open-perplexity && ./myrm setup');
  console.error('   Or pass --webpack explicitly to opt into WASM fallback (not recommended).');
  process.exit(1);
}

ensureBundlerCacheCoherent(bundlerMode);
fs.mkdirSync('.next', { recursive: true });
fs.writeFileSync(BUNDLER_STAMP, `${bundlerMode}\n`, 'utf8');
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
