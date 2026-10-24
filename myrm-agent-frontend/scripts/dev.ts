/**
 * [INPUT]
 * - dev-lock::tryAttachToHealthyDevServer / acquireDevLock (POS: dev-server lock gate)
 * - frontend-dev-pause-gate::probeFrontendDevPause / enforceFrontendDevNotPaused (POS: TS pause gate SSOT)
 * - port-cleanup::APP_DEV_PORT / killListenersOnPort (POS: LISTEN-only port cleanup)
 *
 * [OUTPUT]
 * - Next.js dev server via `node --require next-dev-gate.cjs` + next bin (Turbopack when native SWC present)
 * - Early exit when lock+HTTP prove an existing healthy dev server
 *
 * [POS]
 * Frontend dev entry (`bun run dev` / `dev:lan` / `dev:clean`). Respects shared pause stamp; supervises Next child.
 */
import { type ChildProcess, execFile, spawn, spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import {
  acquireDevLock,
  assertDevLockAvailable,
  readDevLock,
  releaseDevLock,
  tryAttachToHealthyDevServer,
} from './dev-lock';
import { isFrontendDevPaused, probeFrontendDevPause } from './frontend-dev-pause-gate';
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

/** Keep generated namespaces in sync while locale JSON is edited during a long-lived dev session. */
function watchLocaleSources(): void {
  const localesDir = path.join(__dirname, '..', 'locales');
  let timer: NodeJS.Timeout | undefined;
  const resplit = (): void => {
    execFile(process.execPath, [SPLIT_LOCALE_SCRIPT], { cwd: path.join(__dirname, '..') }, () => undefined);
  };
  // persistent:false — the watcher must never keep an attach-and-exit dev.ts alive.
  fs.watch(localesDir, { persistent: false }, (_event, filename) => {
    if (!filename || !filename.endsWith('.json')) {
      return;
    }
    clearTimeout(timer);
    timer = setTimeout(resplit, 500);
    timer.unref();
  });
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
const nextDistDir = process.env.MYRM_NEXT_DIST_DIR?.trim() || '.next-dev';
const STALE_ISOLATED_NEXT_MAX_AGE_MS = 24 * 60 * 60 * 1000;

ensureLocaleNamespaces();
watchLocaleSources();
ensureDevEnvLocal();

function pruneStaleIsolatedNextDirs(): void {
  const activeDistName = path.basename(nextDistDir);
  const now = Date.now();
  let removed = 0;
  for (const entry of fs.readdirSync(process.cwd(), { withFileTypes: true })) {
    if (!entry.isDirectory() || !entry.name.startsWith('.next-isolated-')) {
      continue;
    }
    if (entry.name === activeDistName) {
      continue;
    }
    const target = path.join(process.cwd(), entry.name);
    try {
      const ageMs = now - fs.statSync(target).mtimeMs;
      if (ageMs < STALE_ISOLATED_NEXT_MAX_AGE_MS) {
        continue;
      }
      fs.rmSync(target, { recursive: true, force: true });
      removed += 1;
    } catch {
      // ignore single-dir failures
    }
  }
  if (removed > 0) {
    console.log(`🧹 Pruned ${removed} stale .next-isolated-* director(ies) older than 24h.`);
  }
}

pruneStaleIsolatedNextDirs();

/**
 * A dev cache reset must never delete the desktop production build: `.next` belongs to
 * `next build`, and the desktop shell reads `.next/standalone`. An explicit
 * MYRM_NEXT_DIST_DIR=.next would otherwise let a bundler switch erase the shipped app,
 * leaving the window with no frontend to load. Fail loudly instead of destroying it.
 */
function assertSafeToClearDevDistDir(): void {
  if (path.basename(path.resolve(nextDistDir)) !== '.next') {
    return;
  }
  if (!fs.existsSync(path.join(nextDistDir, 'standalone'))) {
    return;
  }
  throw new Error(
    `Refusing to clear ${nextDistDir}: it contains the desktop standalone build. ` +
      'Point MYRM_NEXT_DIST_DIR at an isolated dev directory (for example .next-dev).',
  );
}

if (clean) {
  assertSafeToClearDevDistDir();
  console.log(`🧹 Cleaning ${nextDistDir} directory...`);
  fs.rmSync(nextDistDir, { recursive: true, force: true });
}

/**
 * Turbopack writes this marker when it detects that its on-disk task database is
 * unusable (the upstream failure mode is a torn persist after a hard kill, which then
 * panic-loops every worker: ~900% CPU while idle, then OOM). A normal restart keeps
 * the poisoned cache and re-enters the loop, so the only recovery is to drop
 * `<distDir>/dev/cache/turbopack` before the next boot.
 */
function recoverPoisonedTurbopackCache(): void {
  const cacheRoot = path.join(process.cwd(), nextDistDir, 'dev', 'cache', 'turbopack');
  if (!fs.existsSync(path.join(cacheRoot, '__turbo_tasks_invalidated_db'))) {
    return;
  }
  try {
    fs.rmSync(cacheRoot, { recursive: true, force: true });
    console.log(
      'TURBO_CACHE_POISON_RECOVERED: turbopack dev cache was marked invalid; removed it before boot',
    );
  } catch (error) {
    console.warn(`TURBO_CACHE_POISON_RECOVERED_FAILED: ${String(error)}`);
  }
}

recoverPoisonedTurbopackCache();

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
        normalizeSharedTsConfig();
        releaseDevLock();
        process.exit(0);
      }, 1000);
    });
  });
}

function refuseIfPauseGateBroken(context: string): void {
  const probe = probeFrontendDevPause();
  if (probe === 'missing_script' || probe === 'check_failed') {
    console.error(`❌ Frontend dev pause gate broken (${probe}) — refusing ${context} (fail-closed).`);
    process.exit(1);
  }
}

/** When paused: reclaim :port (no attach keepalive) then exit — cleanup intent is "no next". */
function reclaimAndExitIfPaused(): void {
  refuseIfPauseGateBroken('dev.ts startup');
  if (!isFrontendDevPaused()) {
    return;
  }
  console.error(`⏸️  Frontend dev paused (bun run cleanup). Reclaiming :${APP_DEV_PORT} and refusing start.`);
  console.error('   Lift pause: bash myrm-agent/scripts/dev/dev-stack.sh frontend-only clear-pause');
  try {
    killListenersOnPort(APP_DEV_PORT, true);
  } catch {
    // ignore
  }
  try {
    releaseDevLock();
  } catch {
    // ignore
  }
  process.exit(0);
}

reclaimAndExitIfPaused();

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

// After attach attempts: block cold start when cleanup wrote a pause stamp.
reclaimAndExitIfPaused();

console.log(`🧹 Freeing port ${APP_DEV_PORT} (myrm-agent-frontend only)...`);
killListenersOnPort(APP_DEV_PORT);
acquireDevLock(APP_DEV_PORT);

/**
 * Restore the shared TypeScript entry files before Next starts.
 *
 * Next writes this lane's dist paths into the shared `tsconfig.json` include list and
 * `next-env.d.ts` imports on every start. `tsconfig.json` opts out structurally by
 * declaring `extends`, but `next-env.d.ts` has no equivalent switch — Next always
 * rewrites it with the current lane's paths. Every lane therefore inherits whatever
 * dist directory ran last, and a lane that exits uncleanly keeps owning the imports
 * until some later teardown strips them.
 *
 * Because each lane is its own process, clearing the previous lane's imports here
 * makes ownership single-writer: a lane always starts from the canonical config and is
 * free to write its own. That is what every lane needs anyway — pointing
 * `next-env.d.ts` at another lane's dist directory is never correct.
 */
function normalizeSharedTsConfig(): void {
  const result = spawnSync('python3', ['scripts/strip_isolated_tsconfig.py'], {
    cwd: process.cwd(),
    encoding: 'utf-8',
  });
  if (result.status !== 0) {
    console.warn('⚠️  strip_isolated_tsconfig.py exited non-zero; continuing with Next startup');
  }
}

normalizeSharedTsConfig();

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
  if (!pkg) {
    return null;
  }
  const pkgDir = path.join(process.cwd(), 'node_modules', pkg);
  return fs.existsSync(pkgDir) ? pkg : null;
}

const forceWebpack = args.includes('--webpack');
const bundlerMode = forceWebpack ? 'webpack' : 'turbopack';
const BUNDLER_STAMP = path.join(nextDistDir, 'dev-bundler-mode');

function ensureBundlerCacheCoherent(mode: string): void {
  if (clean) {
    return;
  }
  try {
    if (fs.existsSync(BUNDLER_STAMP)) {
      const previous = fs.readFileSync(BUNDLER_STAMP, 'utf8').trim();
      if (previous && previous !== mode) {
        assertSafeToClearDevDistDir();
        console.log(`🧹 Dev bundler changed (${previous} → ${mode}) — clearing ${nextDistDir} cache...`);
        fs.rmSync(nextDistDir, { recursive: true, force: true });
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
fs.mkdirSync(nextDistDir, { recursive: true });
fs.writeFileSync(BUNDLER_STAMP, `${bundlerMode}\n`, 'utf8');
if (bindLan) {
  nextArgs.push('-H', '0.0.0.0');
  console.log(`🌐 LAN bind enabled (0.0.0.0:${APP_DEV_PORT}) — use intranet IP from Settings → System`);
}

console.log(`🚀 Starting Next.js on port ${APP_DEV_PORT}...`);
const nextBin = path.join(process.cwd(), 'node_modules', 'next', 'dist', 'bin', 'next');
const preloadGate = path.join(__dirname, 'next-dev-gate.cjs');
// 开发期内存的真实构成（实测 vmmap）：Turbopack 内存中的模块图/编译产物占绝大多数，
// V8/JSC 堆只有数百 MB。因此 --max-old-space-size 无法约束整体占用，只有明确改用 Node
// 运行时（Bun 是 JSC，不认 V8 参数）时才有意义，故仅在 Node 下按需追加。
const runtimeIsNode = !process.versions.bun;
const maxOldSpace = process.env.NODE_MAX_OLD_SPACE?.trim();
const nodeArgs = runtimeIsNode && maxOldSpace ? [`--max-old-space-size=${maxOldSpace}`] : [];
nodeArgs.push('--require', preloadGate, nextBin, ...nextArgs.slice(1));
const child = spawn(process.execPath, nodeArgs, {
  stdio: 'inherit',
  detached: false,
});

setupSignalHandlers(child);

child.on('exit', (code) => {
  console.log('🏁 Next.js exited with code:', code);
  killListenersOnPort(APP_DEV_PORT, true);
  normalizeSharedTsConfig();
  releaseDevLock();
  process.exit(code ?? 0);
});

child.on('error', (err) => {
  console.error('❌ Failed to start Next.js:', err);
  killListenersOnPort(APP_DEV_PORT, true);
  releaseDevLock();
  process.exit(1);
});
