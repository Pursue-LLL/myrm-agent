// Live-regression harness: an isolated proxy + real Chrome (temp profile, random port)
// and real chrome-devtools-mcp processes. Never touches the production :9410.
import { spawn } from 'node:child_process';
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
    /** @param {string} proxyDir directory containing pipe-cdp-proxy.mjs and node_modules/ws */
    constructor(proxyDir = AGENT_DIR) {
        this.proxyDir = proxyDir;
    }

    async start() {
        this.port = await freePort();
        if (this.port === 9410) throw new Error('refusing to use the production port');
        this.base = `http://127.0.0.1:${this.port}`;
        this.profile = fs.mkdtempSync(path.join(os.tmpdir(), 'chrome-agent-live-'));
        this.logPath = path.join(this.profile, 'proxy.log');
        const log = fs.openSync(this.logPath, 'w');
        this.proc = spawn(process.execPath, [
            path.join(this.proxyDir, 'pipe-cdp-proxy.mjs'),
            '--port', String(this.port),
            '--chrome-path', this.#headlessChrome(),
            '--user-data-dir', path.join(this.profile, 'chrome'),
            '--initial-url', 'about:blank',
        ], { stdio: ['ignore', log, log], detached: true });
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

    log() {
        return fs.readFileSync(this.logPath, 'utf8');
    }

    /** SIGTERM the proxy; its shutdown handler also terminates Chrome. */
    stop() {
        try { process.kill(this.proc.pid, 'SIGTERM'); } catch { /* already gone */ }
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

    /** Passive CDP listener that records every Target.attached/detached event it receives. */
    async listener() {
        const version = await (await fetch(`${this.base}/json/version`)).json();
        const ws = new WebSocket(version.webSocketDebuggerUrl);
        await new Promise((resolve) => ws.addEventListener('open', resolve, { once: true }));
        const events = [];
        ws.addEventListener('message', (e) => {
            const msg = JSON.parse(e.data);
            if (msg.method === 'Target.attachedToTarget' || msg.method === 'Target.detachedFromTarget') {
                events.push({ method: msg.method, sessionId: msg.params.sessionId, at: Date.now() });
            }
        });
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
