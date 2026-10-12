// Teardown of one live-test sandbox (proxy + its Chrome + temp profile). The harness runs it from
// stop(); reaper.mjs runs it when the test runner dies without getting the chance to stop.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

/** Left in the profile dir once a teardown started, so reaper.mjs knows there is nothing to do. */
export const STOPPED_MARKER = '.stopped';
const PROXY_PID_FILE = 'proxy.pid';
const RETIRED_SOCKETS_FILE = 'retired-socket-dirs';

export const recordProxyPid = (profile, pid) => fs.writeFileSync(path.join(profile, PROXY_PID_FILE), String(pid));

/** True for a com.google.Chrome.* directory directly inside the temp dir: the only kind we ever remove. */
function isChromeSocketDir(dir) {
    try {
        return path.basename(dir).startsWith('com.google.Chrome.')
            && fs.realpathSync(path.dirname(dir)) === fs.realpathSync(os.tmpdir());
    } catch {
        return false;
    }
}

/**
 * Chrome keeps its singleton socket in a com.google.Chrome.* dir beside the profile. Read it
 * while Chrome runs: on exit Chrome removes the link and leaves the dir behind.
 */
function socketDirOf(profile) {
    try {
        const dir = path.dirname(fs.readlinkSync(path.join(profile, 'chrome', 'SingletonSocket')));
        return isChromeSocketDir(dir) ? dir : null;
    } catch {
        return null;
    }
}

/** Remember the socket dir of a Chrome that is about to exit (restart), so the final teardown removes it too. */
export function retireSocketDir(profile) {
    const dir = socketDirOf(profile);
    if (dir) fs.appendFileSync(path.join(profile, RETIRED_SOCKETS_FILE), `${dir}\n`);
}

function retiredSocketDirs(profile) {
    try {
        return fs.readFileSync(path.join(profile, RETIRED_SOCKETS_FILE), 'utf8').split('\n').filter(isChromeSocketDir);
    } catch {
        return [];
    }
}

/** SIGTERM the proxy (its shutdown handler also terminates Chrome), unless the pid was reused by something else. */
function terminateProxy(profile) {
    try {
        const pid = Number(fs.readFileSync(path.join(profile, PROXY_PID_FILE), 'utf8'));
        const command = execFileSync('ps', ['-o', 'command=', '-p', String(pid)], { encoding: 'utf8' });
        if (command.includes(profile)) process.kill(pid, 'SIGTERM');
    } catch { /* no pid file, or the proxy is already gone */ }
}

/** Blocks until no process runs from this sandbox's unique profile path; SIGKILLs stragglers after 8 s. */
export function waitUntilGone(profile) {
    const running = () => {
        try { return execFileSync('pgrep', ['-f', '--', profile]).length > 0; } catch { return false; }
    };
    for (let waited = 0; running(); waited += 200) {
        if (waited >= 8000) {
            try { execFileSync('pkill', ['-9', '-f', '--', profile]); } catch { /* none left */ }
            return;
        }
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 200);
    }
}

/**
 * A Chrome killed during its first-launch component install leaves the downloaded CRX
 * (.com.google.Chrome.*), its unpack dir (scoped_dir*: a CRX, maybe CRX_INSTALL) or the
 * updater download dir (com.google.Chrome.chrome_chrome_url_fetcher_.*) in the temp dir. Only
 * such leftovers that appeared after the sandbox started and no process holds open are removed.
 */
function sweepChromeTempLeftovers(startedAt) {
    const tmp = os.tmpdir();
    const isCrx = (file) => {
        const fd = fs.openSync(file, 'r');
        try {
            const magic = Buffer.alloc(4);
            fs.readSync(fd, magic, 0, 4, 0);
            return magic.toString() === 'Cr24';
        } finally {
            fs.closeSync(fd);
        }
    };
    // A download another Chrome is still writing holds its file open.
    const inUse = (entry, stat) => {
        try {
            return execFileSync('lsof', ['-t', ...(stat.isDirectory() ? ['+D'] : []), entry], { stdio: ['ignore', 'pipe', 'ignore'] }).length > 0;
        } catch {
            return false;
        }
    };
    const isLeftover = (name, entry, stat) => {
        if (/^\.com\.google\.Chrome\.[A-Za-z0-9]{6}$/.test(name)) return stat.isFile() && isCrx(entry);
        if (name.startsWith('com.google.Chrome.chrome_chrome_url_fetcher_.')) return stat.isDirectory();
        if (!name.startsWith('scoped_dir') || !stat.isDirectory()) return false;
        const inside = fs.readdirSync(entry);
        return inside.some((f) => f.startsWith('.com.google.Chrome.'))
            && inside.every((f) => f === 'CRX_INSTALL' || f.startsWith('.com.google.Chrome.'));
    };
    for (const name of fs.readdirSync(tmp)) {
        const entry = path.join(tmp, name);
        try {
            const stat = fs.statSync(entry);
            if (stat.mtimeMs >= startedAt && isLeftover(name, entry, stat) && !inUse(entry, stat)) {
                fs.rmSync(entry, { recursive: true, force: true });
            }
        } catch { /* vanished or unreadable: not ours to clean */ }
    }
}

/**
 * Stop the sandbox's proxy and Chrome, then delete everything the run left in the temp dir,
 * retrying while Chrome is still flushing its profile. keepLog leaves proxy.log behind for
 * diagnosing a failed run. Idempotent.
 */
export function removeSandbox({ profile, startedAt, keepLog = false }) {
    if (!fs.existsSync(profile)) return;
    fs.writeFileSync(path.join(profile, STOPPED_MARKER), '');
    const rm = (target) => fs.rmSync(target, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
    const socketDirs = [...retiredSocketDirs(profile), socketDirOf(profile)].filter(Boolean);
    terminateProxy(profile);
    waitUntilGone(profile);
    sweepChromeTempLeftovers(startedAt);
    try {
        for (const dir of socketDirs) rm(dir);
        if (keepLog) {
            for (const name of ['chrome', 'chrome-headless.sh', PROXY_PID_FILE, RETIRED_SOCKETS_FILE]) {
                rm(path.join(profile, name));
            }
        } else {
            rm(profile);
        }
    } catch (err) {
        console.error(`could not remove ${profile}: ${err.message}`);
    }
}
