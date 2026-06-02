import { execSync } from 'child_process';
import { APP_DEV_PORT, killListenersOnPort, listPidsOnPort } from './port-cleanup';

console.log(`🧹 Cleaning up myrm-agent-frontend dev port :${APP_DEV_PORT} only...\n`);

function showPortProcesses(port: number) {
  const pidList = listPidsOnPort(port);
  if (pidList.length === 0) {
    console.log(`✅ Port ${port} is free.\n`);
    return;
  }
  console.log(`Found ${pidList.length} process(es) on port ${port}:`);
  pidList.forEach((pid) => {
    try {
      const info = execSync(`ps -p ${pid} -o pid,ppid,%cpu,%mem,etime,command | tail -1`, {
        encoding: 'utf-8',
      }).trim();
      console.log(`  ${info}`);
    } catch {
      console.log(`  PID: ${pid}`);
    }
  });
  console.log('');
}

showPortProcesses(APP_DEV_PORT);
const cleanedCount = killListenersOnPort(APP_DEV_PORT, true);

console.log('📊 Current memory usage:');
try {
  console.log(execSync('vm_stat | head -5', { encoding: 'utf-8' }));
} catch {
  // ignore
}

console.log(`\n✨ Cleanup complete! Terminated ${cleanedCount} process(es) on :${APP_DEV_PORT}.`);
console.log('ℹ️  Other ports (e.g. myrm-website :3002) are untouched.');
