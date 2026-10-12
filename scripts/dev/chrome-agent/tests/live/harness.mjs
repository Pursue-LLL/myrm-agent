// Live-regression harness: an isolated proxy + real Chrome (temp profile, random port)
// and real chrome-devtools-mcp processes. Never touches the production :9410.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { recordProxyPid, removeSandbox, retireSocketDir, waitUntilGone } from './sandbox-cleanup.mjs';

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
        this.#spawnReaper();
        await this.#ready();
    }

    /** Restarts the proxy and its Chrome on the same port and profile, as a service restart would. */
    async restart() {
        retireSocketDir(this.profile);
        process.kill(this.proc.pid, 'SIGTERM');
        waitUntilGone(this.profile);
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
        recordProxyPid(this.profile, this.proc.pid);
    }

    /**
     * stop() cannot run when this process is SIGKILLed. A watchdog in its own process group then
     * tears the sandbox down; it gets the profile through the environment because the teardown's
     * `pgrep -f <profile>` would otherwise match the watchdog itself.
     */
    #spawnReaper() {
        spawn(process.execPath, [path.join(HERE, 'reaper.mjs')], {
            stdio: 'ignore',
            detached: true,
            env: {
                ...process.env,
                LIVE_REAPER_PROFILE: this.profile,
                LIVE_REAPER_RUNNER: String(process.pid),
                LIVE_REAPER_STARTED: String(this.startedAt),
            },
        }).unref();
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
     * Stop the proxy and Chrome, then delete everything the run left in the temp dir. A failed run
     * passes keepLog to leave proxy.log behind for diagnosis. Idempotent.
     */
    stop({ keepLog = false } = {}) {
        if (this.stopped || !this.proc) return;
        this.stopped = true;
        removeSandbox({ profile: this.profile, startedAt: this.startedAt, keepLog });
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
