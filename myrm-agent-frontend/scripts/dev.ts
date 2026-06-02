import { spawn } from 'child_process';
import fs from 'fs';
import { APP_DEV_PORT, killListenersOnPort } from './port-cleanup';

const args = process.argv.slice(2);
const clean = args.includes('--clean');

if (clean) {
  console.log('🧹 Cleaning .next directory...');
  fs.rmSync('.next', { recursive: true, force: true });
}

function setupSignalHandlers(childPid: number) {
  const signals: NodeJS.Signals[] = ['SIGINT', 'SIGTERM', 'SIGHUP'];

  signals.forEach((signal) => {
    process.on(signal, () => {
      console.log(`\n🛑 Received ${signal}, terminating Next.js on :${APP_DEV_PORT}...`);
      try {
        process.kill(-childPid, 'SIGTERM');
      } catch {
        // ignore
      }
      setTimeout(() => {
        killListenersOnPort(APP_DEV_PORT, true);
        process.exit(0);
      }, 1000);
    });
  });
}

console.log(`🧹 Freeing port ${APP_DEV_PORT} (myrm-agent-frontend only)...`);
killListenersOnPort(APP_DEV_PORT);

const bindLan =
  process.env.WEBUI_DEV_BIND_ALL === '1' || process.env.WEBUI_DEV_BIND_ALL === 'true' || args.includes('--lan');
const nextArgs = ['next', 'dev', '-p', String(APP_DEV_PORT)];
if (bindLan) {
  nextArgs.push('-H', '0.0.0.0');
  console.log(`🌐 LAN bind enabled (0.0.0.0:${APP_DEV_PORT}) — use intranet IP from Settings → System`);
}

console.log(`🚀 Starting Next.js on port ${APP_DEV_PORT}...`);
const child = spawn('bunx', [...nextArgs], {
  stdio: 'inherit',
  detached: true,
});

if (child.pid) {
  setupSignalHandlers(child.pid);
}

child.on('exit', (code) => {
  console.log('🏁 Next.js exited with code:', code);
  killListenersOnPort(APP_DEV_PORT, true);
  process.exit(code ?? 0);
});

child.on('error', (err) => {
  console.error('❌ Failed to start Next.js:', err);
  killListenersOnPort(APP_DEV_PORT, true);
  process.exit(1);
});
