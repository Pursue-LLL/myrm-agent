// Live-regression harness: an isolated proxy + real Chrome (temp profile, random port)
// and real chrome-devtools-mcp processes. Never touches the production :9410.
import { execFileSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const AGENT_DIR = path.resolve(HERE, '../..');
export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function findMcpEntry() {
    if (process.env.CHROME_DEVTOOLS_MCP_JS) return process.env.CHROME_DEVTOOLS_MCP_JS;
    const npxRoot = path.join(os.homedir(), '.npm/_npx');
    if (!fs.existsSync(npxRoot)) return null;
    for (const dir of fs.readdirSync(npxRoot)) {
        const entry = path.join(npxRoot, dir, 'node_modules/chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js');
        if (fs.existsSync(entry)) return entry;
    }
    return null;
}

function freePort() {
    return new Promise((resolve, reject) => {
        const srv = net.createServer();
        srv.listen(0, '127.0.0.1', () => {
            const { port } = srv.address();
            srv.close(() => resolve(port));
        });
        srv.on('error', reject);
    });
}

/** Chrome binary for the proxy: arm64 launcher on macOS, CHROME_PATH override elsewhere. */
function chromePath() {
    if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
    const launcher = path.join(AGENT_DIR, 'chrome-arm64-launcher.sh');
    return process.platform === 'darwin' && fs.existsSync(launcher)
        ? launcher
        : '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
}

export class SandboxProxy {
    /**
     * @param {string} proxyDir directory containing pipe-cdp-proxy.mjs and node_modules/ws
     * @param {Record<string, string>} env extra proxy environment; the idle-tab pool is off unless
     *   CHROME_AGENT_MIN_IDLE_TABS is set, so scenarios that count tabs stay deterministic
     */
    constructor(proxyDir = AGENT_DIR, env = {}) {
        this.proxyDir = proxyDir;
        this.env = { CHROME_AGENT_MIN_IDLE_TABS: '0', ...env };
        this.retiredSocketDirs = [];
    }

    async start() {
        this.port = await freePort();
        if (this.port === 9410) throw new Error('refusing to use the production port');
        this.base = `http://127.0.0.1:${this.port}`;
        this.profile = fs.mkdtempSync(path.join(os.tmpdir(), 'chrome-agent-live-'));
        this.logPath = path.join(this.profile, 'proxy.log');
        this.startedAt = Date.now();
        this.#spawn('w');
        // The proxy is detached, so a crashed or interrupted test run would orphan it with Chrome
        // and the profile; every way out of this process must pass through stop().
        // An operator's interrupt (130) is not a failure worth a log; any other non-zero exit is.
        process.once('exit', (code) => this.stop({ keepLog: code !== 0 && code !== 130 }));
        for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => process.exit(130));
        await this.#ready();
    }

    /** Restarts the proxy and its Chrome on the same port and profile, as a service restart would. */
    async restart() {
        this.retiredSocketDirs.push(this.#socketDir());
        process.kill(this.proc.pid, 'SIGTERM');
        this.#waitUntilGone();
        this.#spawn('a');
        await this.#ready();
    }

    #spawn(logFlag) {
        const log = fs.openSync(this.logPath, logFlag);
        this.proc = spawn(process.execPath, [
            path.join(this.proxyDir, 'pipe-cdp-proxy.mjs'),
            '--port', String(this.port),
            '--chrome-path', this.#headlessChrome(),
            '--user-data-dir', path.join(this.profile, 'chrome'),
            '--initial-url', 'about:blank',
        ], { stdio: ['ignore', log, log], detached: true, env: { ...process.env, ...this.env } });
        fs.closeSync(log);
    }

    async #ready() {
        for (let i = 0; i < 60; i++) {
            await sleep(500);
            try {
                const status = await (await fetch(`${this.base}/proxy/status`)).json();
                if (status.chromeRunning && status.knownSessions > 0) return;
            } catch { /* proxy not listening yet */ }
        }
        throw new Error(`sandbox proxy did not become ready; see ${this.logPath}`);
    }

    /**
     * Wrapper that adds --headless=new: a windowed Chrome started by tests activates the app and
     * steals the user's keyboard focus on macOS even when its window is positioned off-screen.
     * Set LIVE_HEADED=1 to watch a run.
     */
    #headlessChrome() {
        if (process.env.LIVE_HEADED === '1') return chromePath();
        const wrapper = path.join(this.profile, 'chrome-headless.sh');
        fs.writeFileSync(wrapper, `#!/bin/sh\nexec "${chromePath()}" "$@" --headless=new\n`, { mode: 0o755 });
        return wrapper;
    }

    async status() {
        return (await fetch(`${this.base}/proxy/status`)).json();
    }

    /**
     * SIGTERM the proxy (its shutdown handler also terminates Chrome), then delete everything the
     * run left in the temp dir, retrying while Chrome is still flushing its profile. A failed run
     * passes keepLog to leave proxy.log behind for diagnosis. Idempotent.
     */
    stop({ keepLog = false } = {}) {
        if (this.stopped || !this.proc) return;
        this.stopped = true;
        const rm = (target) => fs.rmSync(target, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
        const socketDirs = [...this.retiredSocketDirs, this.#socketDir()].filter(Boolean);
        try { process.kill(this.proc.pid, 'SIGTERM'); } catch { /* already gone */ }
        this.#waitUntilGone();
        this.#sweepChromeTempLeftovers();
        try {
            for (const dir of socketDirs) rm(dir);
            if (keepLog) {
                rm(path.join(this.profile, 'chrome'));
                rm(path.join(this.profile, 'chrome-headless.sh'));
            } else {
                rm(this.profile);
            }
        } catch (err) {
            console.error(`could not remove ${this.profile}: ${err.message}`);
        }
    }

    /**
     * Chrome keeps its singleton socket in a com.google.Chrome.* dir beside the profile. Read it
     * while Chrome runs: on exit Chrome removes the link and leaves the dir behind.
     */
    #socketDir() {
        try {
            const dir = path.dirname(fs.readlinkSync(path.join(this.profile, 'chrome', 'SingletonSocket')));
            const inTmp = fs.realpathSync(path.dirname(dir)) === fs.realpathSync(os.tmpdir());
            return inTmp && path.basename(dir).startsWith('com.google.Chrome.') ? dir : null;
        } catch {
            return null;
        }
    }

    /**
     * A Chrome killed during its first-launch component install leaves the downloaded CRX
     * (.com.google.Chrome.*), its unpack dir (scoped_dir*: a CRX, maybe CRX_INSTALL) or the
     * updater download dir (com.google.Chrome.chrome_chrome_url_fetcher_.*) in the temp dir. Only
     * such leftovers that appeared after this sandbox started and no process holds open are removed.
     */
    #sweepChromeTempLeftovers() {
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
                if (stat.mtimeMs >= this.startedAt && isLeftover(name, entry, stat) && !inUse(entry, stat)) {
                    fs.rmSync(entry, { recursive: true, force: true });
                }
            } catch { /* vanished or unreadable: not ours to clean */ }
        }
    }

    /** Blocks until no process runs from this run's unique profile path; SIGKILLs stragglers after 8 s. */
    #waitUntilGone() {
        const running = () => {
            try { return execFileSync('pgrep', ['-f', '--', this.profile]).length > 0; } catch { return false; }
        };
        for (let waited = 0; running(); waited += 200) {
            if (waited >= 8000) {
                try { execFileSync('pkill', ['-9', '-f', '--', this.profile]); } catch { /* none left */ }
                return;
            }
            Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 200);
        }
    }

    async chromePages() {
        const list = await (await fetch(`${this.base}/json/list`)).json();
        return list.filter((t) => t.type === 'page').map((t) => ({ id: t.id, url: t.url }));
    }

    /**
     * Make Chrome hold exactly `count` about:blank pages. New pages are opened before the old
     * ones are closed so the browser never has zero tabs (closing all first intermittently left
     * it with none under load).
     */
    async resetPages(count = 3) {
        const cdpClient = await this.cdp();
        const stale = await this.chromePages();
        for (let i = 0; i < count; i++) {
            await cdpClient.send('Target.createTarget', { url: 'about:blank' });
        }
        for (const page of stale) {
            await cdpClient.send('Target.closeTarget', { targetId: page.id });
        }
        cdpClient.close();
        await sleep(800);
    }

    /** Bare CDP client on the browser endpoint (no MCP). */
    async cdp() {
        const version = await (await fetch(`${this.base}/json/version`)).json();
        const ws = new WebSocket(version.webSocketDebuggerUrl);
        await new Promise((resolve) => ws.addEventListener('open', resolve, { once: true }));
        let nextId = 1;
        const pending = new Map();
        ws.addEventListener('message', (e) => {
            const msg = JSON.parse(e.data);
            if (msg.id && pending.has(msg.id)) {
                pending.get(msg.id)(msg);
                pending.delete(msg.id);
            }
        });
        const send = (method, params = {}, sessionId) => new Promise((resolve) => {
            const id = nextId++;
            pending.set(id, resolve);
            ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
        });
        return { send, close: () => ws.close() };
    }

    /**
     * Passive CDP listener that records every Target.attached/detached event it receives.
     * It enables browser-level auto-attach so it is told about every shared session up front:
     * an event whose session has no `type` therefore belongs to a session nobody announced to it.
     */
    async listener() {
        const version = await (await fetch(`${this.base}/json/version`)).json();
        const ws = new WebSocket(version.webSocketDebuggerUrl);
        await new Promise((resolve) => ws.addEventListener('open', resolve, { once: true }));
        const events = [];
        const typeOf = new Map();
        const autoAttached = new Promise((resolve) => {
            ws.addEventListener('message', (e) => {
                const msg = JSON.parse(e.data);
                if (msg.id === 1) resolve();
                if (msg.method === 'Target.attachedToTarget') typeOf.set(msg.params.sessionId, msg.params.targetInfo?.type);
                if (msg.method === 'Target.attachedToTarget' || msg.method === 'Target.detachedFromTarget') {
                    // `type` is the target type announced when this session attached ('other' = Chrome-internal
                    // targets that come and go on their own); undefined = a session never announced to this listener.
                    events.push({ method: msg.method, sessionId: msg.params.sessionId, type: typeOf.get(msg.params.sessionId), at: Date.now() });
                }
            });
        });
        ws.send(JSON.stringify({ id: 1, method: 'Target.setAutoAttach', params: { autoAttach: true, waitForDebuggerOnStart: false, flatten: true } }));
        await autoAttached;
        return { events, close: () => ws.close() };
    }

    mcp(name) {
        return new Mcp(name, this.base);
    }
}

export class Mcp {
    constructor(name, browserUrl) {
        this.name = name;
        this.browserUrl = browserUrl;
        this.nextId = 1;
        this.pending = new Map();
        this.buffer = '';
    }

    async start() {
        const entry = findMcpEntry();
        if (!entry) throw new Error('chrome-devtools-mcp not found (set CHROME_DEVTOOLS_MCP_JS)');
        this.proc = spawn(process.execPath, [entry, '--browserUrl', this.browserUrl, '--no-usage-statistics'], {
            stdio: ['pipe', 'pipe', 'ignore'],
        });
        this.proc.stdout.on('data', (chunk) => {
            this.buffer += chunk.toString();
            let nl;
            while ((nl = this.buffer.indexOf('\n')) >= 0) {
                const line = this.buffer.slice(0, nl).trim();
                this.buffer = this.buffer.slice(nl + 1);
                if (!line) continue;
                let msg;
                try { msg = JSON.parse(line); } catch { continue; }
                if (msg.id !== undefined && this.pending.has(msg.id)) {
                    this.pending.get(msg.id)(msg);
                    this.pending.delete(msg.id);
                }
            }
        });
        await this.rpc('initialize', {
            protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: `live-${this.name}`, version: '0' },
        });
        this.proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n');
    }

    rpc(method, params = {}, timeoutMs = 30000) {
        return new Promise((resolve, reject) => {
            const id = this.nextId++;
            const timer = setTimeout(() => {
                this.pending.delete(id);
                reject(new Error(`${this.name} ${method} timed out`));
            }, timeoutMs);
            this.pending.set(id, (msg) => { clearTimeout(timer); resolve(msg); });
            this.proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
        });
    }

    /** Returns { text, isError }; transport-level errors are reported as isError too. */
    async tool(name, args = {}) {
        const msg = await this.rpc('tools/call', { name, arguments: args });
        if (msg.error) return { text: JSON.stringify(msg.error), isError: true };
        const text = (msg.result?.content ?? []).map((c) => c.text ?? `[${c.type}]`).join('\n');
        return { text, isError: Boolean(msg.result?.isError) };
    }

    /** Page ids and urls the MCP currently believes exist, parsed from list_pages. */
    async pages() {
        const { text } = await this.tool('list_pages');
        return [...text.matchAll(/^(\d+): (\S+)/gm)].map((m) => ({ id: Number(m[1]), url: m[2] }));
    }

    stop() {
        try { this.proc.stdin.end(); } catch { /* closed */ }
        try { this.proc.kill('SIGTERM'); } catch { /* gone */ }
    }
}
