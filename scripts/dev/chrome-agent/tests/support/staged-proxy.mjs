// Proxy-level fixture: the real pipe-cdp-proxy.mjs, installed the way the machine-level installer
// installs it (top-level modules only, `ws` from node_modules), talking to a scripted stand-in for
// Chrome (fake-chrome-relay.mjs). It covers the wiring inside pipe-cdp-proxy.mjs that unit tests of
// its modules cannot reach, and fails when the bundle is not self-contained.
//
// `ws` is not a dependency of the source tree: run `npm ci` in scripts/dev/chrome-agent, or install
// the machine-level bundle (its node_modules is the fallback). CHROME_AGENT_PROXY_DIR runs the tests
// against another bundle directory instead (e.g. a pre-fix copy as a negative control).
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const AGENT_DIR = path.resolve(HERE, '../..');
const RELAY = path.join(HERE, 'fake-chrome-relay.mjs');
const BUNDLE_OVERRIDE = process.env.CHROME_AGENT_PROXY_DIR;
/** A proxy outliving a SIGKILLed test run is bounded by this alarm. */
const DEADMAN_SECONDS = 180;
const WAIT_MS = 10_000;

/** Return from a FakeChrome handler to leave a request unanswered until the test replies itself. */
export const HOLD = Symbol('hold');

const wsDir = [
    BUNDLE_OVERRIDE && path.join(BUNDLE_OVERRIDE, 'node_modules/ws'),
    path.join(AGENT_DIR, 'node_modules/ws'),
    path.join(
        process.env.MYRM_CHROME_AGENT_INSTALL_DIR ?? path.join(os.userInfo().homedir, '.local/lib/myrm-chrome-agent'),
        'current/node_modules/ws',
    ),
].find((dir) => dir && fs.existsSync(path.join(dir, 'wrapper.mjs')));

/** Falsy when the fixture can run; otherwise the reason to pass to `test(..., { skip })`. */
export const skipReason = wsDir ? false : 'ws is not installed (run `npm ci` in scripts/dev/chrome-agent)';

const { default: WebSocketClient } = wsDir
    ? await import(pathToFileURL(path.join(wsDir, 'wrapper.mjs')).href)
    : { default: null };

let stagedBundle;

/** Copy what the installer copies (top-level *.mjs and the package files), then provide `ws`. */
function bundleDir() {
    if (BUNDLE_OVERRIDE) return BUNDLE_OVERRIDE;
    if (stagedBundle) return stagedBundle;
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'chrome-agent-bundle-'));
    for (const name of fs.readdirSync(AGENT_DIR)) {
        if (name.endsWith('.mjs') || name === 'package.json' || name === 'package-lock.json') {
            fs.copyFileSync(path.join(AGENT_DIR, name), path.join(dir, name));
        }
    }
    fs.mkdirSync(path.join(dir, 'node_modules'));
    fs.symlinkSync(wsDir, path.join(dir, 'node_modules/ws'));
    process.once('exit', () => fs.rmSync(dir, { recursive: true, force: true }));
    stagedBundle = dir;
    return dir;
}

function freePort() {
    return new Promise((resolve, reject) => {
        const server = net.createServer();
        server.listen(0, '127.0.0.1', () => {
            const { port } = server.address();
            server.close(() => resolve(port));
        });
        server.on('error', reject);
    });
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** The test's end of the relay: records what the proxy forwards and answers as Chrome would. */
class FakeChrome {
    /** Requests and notifications the proxy forwarded, in arrival order (ids are the proxy's). */
    received = [];
    #handlers = new Map();
    #socket = null;

    static async listen() {
        const chrome = new FakeChrome();
        chrome.server = net.createServer((socket) => chrome.#attach(socket));
        await new Promise((resolve) => chrome.server.listen(0, '127.0.0.1', resolve));
        chrome.port = chrome.server.address().port;
        return chrome;
    }

    #attach(socket) {
        this.#socket = socket;
        let lines = '';
        socket.on('data', (chunk) => {
            lines += chunk.toString('utf8');
            let end;
            while ((end = lines.indexOf('\n')) !== -1) {
                const line = lines.slice(0, end);
                lines = lines.slice(end + 1);
                if (line) this.#onRequest(JSON.parse(line).fromProxy);
            }
        });
        socket.on('error', () => {});
    }

    #onRequest(msg) {
        this.received.push(msg);
        if (msg.id === undefined) return;
        const result = this.#handlers.has(msg.method) ? this.#handlers.get(msg.method)(msg) : {};
        if (result !== HOLD) this.reply(msg.id, result, msg.sessionId);
    }

    /** Answer `method` with the handler's result object (default `{}`), or return HOLD to answer later. */
    on(method, handler) {
        this.#handlers.set(method, handler);
    }

    send(message) {
        this.#socket.write(`${JSON.stringify({ toProxy: message })}\n`);
    }

    reply(id, result = {}, sessionId) {
        this.send({ id, result, ...(sessionId && { sessionId }) });
    }

    fail(id, message, code = -32000) {
        this.send({ id, error: { code, message } });
    }

    event(method, params = {}, sessionId) {
        this.send({ method, params, ...(sessionId && { sessionId }) });
    }

    requests(method) {
        return this.received.filter((msg) => msg.method === method);
    }

    async waitFor(predicate, timeoutMs = WAIT_MS) {
        const deadline = Date.now() + timeoutMs;
        while (Date.now() < deadline) {
            const found = this.received.find(predicate);
            if (found) return found;
            await sleep(20);
        }
        throw new Error(`Chrome never received the awaited message; got [${this.received.map((m) => m.method)}]`);
    }

    close() {
        this.#socket?.destroy();
        this.server.close();
    }
}

/** A CDP client on the proxy's WebSocket, as one chrome-devtools-mcp process would be. */
class CdpClient {
    nextId = 1;
    /** Messages that were not a reply to a request (events). */
    events = [];
    #pending = new Map();

    constructor(ws) {
        this.ws = ws;
        this.closed = new Promise((resolve) => ws.once('close', resolve));
        // A reply that can no longer arrive must not leave its timeout armed.
        this.closed.then(() => {
            for (const { timer } of this.#pending.values()) clearTimeout(timer);
            this.#pending.clear();
        });
        ws.on('message', (data) => {
            const msg = JSON.parse(data.toString());
            const request = msg.id === undefined ? undefined : this.#pending.get(msg.id);
            if (request) {
                this.#pending.delete(msg.id);
                clearTimeout(request.timer);
                request.resolve(msg);
            } else {
                this.events.push(msg);
            }
        });
    }

    /** Resolves with the proxy's reply (result or error); rejects when none arrives in time. */
    send(method, params = {}, sessionId) {
        const id = this.nextId++;
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
                this.#pending.delete(id);
                reject(new Error(`no reply to ${method}`));
            }, WAIT_MS);
            this.#pending.set(id, { resolve, timer });
            this.ws.send(JSON.stringify({ id, method, params, ...(sessionId && { sessionId }) }));
        });
    }

    /** A CDP message without an id: nothing can be answered to it. */
    notify(method, params = {}) {
        this.ws.send(JSON.stringify({ method, params }));
    }

    close() {
        this.ws.close();
        return this.closed;
    }

    /** Drop the connection without a close handshake, as a killed client process does. */
    abort() {
        this.ws.terminate();
        return this.closed;
    }
}

/**
 * Start the proxy on a free port against a FakeChrome. `env` overrides the proxy's environment; the
 * idle-tab pool is off and the E2E-URL guard is on unless the test says otherwise.
 */
export async function startProxy({ env = {} } = {}) {
    const chrome = await FakeChrome.listen();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'chrome-agent-unit-'));
    const launcher = path.join(profile, 'chrome');
    fs.writeFileSync(launcher, `#!/bin/sh\nexec "${process.execPath}" "${RELAY}" "$@"\n`, { mode: 0o755 });
    const port = await freePort();
    const logs = [];
    const proc = spawn('perl', [
        '-e', 'alarm shift; exec @ARGV', String(DEADMAN_SECONDS),
        process.execPath, path.join(bundleDir(), 'pipe-cdp-proxy.mjs'),
        '--port', String(port), '--chrome-path', launcher, '--user-data-dir', path.join(profile, 'data'),
    ], {
        stdio: ['ignore', 'pipe', 'pipe'],
        env: {
            ...process.env,
            CHROME_AGENT_MIN_IDLE_TABS: '0',
            MYRM_CHROME_AGENT_ALLOW_E2E_URLS: '0',
            MYRM_CHROME_AGENT_FOREGROUND: '0',
            PROXY_DEBUG: '0',
            FAKE_CHROME_CONTROL_PORT: String(chrome.port),
            ...env,
        },
    });
    for (const stream of [proc.stdout, proc.stderr]) {
        let partial = '';
        stream.on('data', (chunk) => {
            const parts = (partial + chunk.toString('utf8')).split('\n');
            partial = parts.pop();
            logs.push(...parts);
        });
    }
    const exited = new Promise((resolve) => proc.once('exit', resolve));
    process.once('exit', () => proc.kill('SIGKILL'));

    const base = `http://127.0.0.1:${port}`;
    const status = async () => (await fetch(`${base}/proxy/status`)).json();
    let stopped = false;
    const stop = async () => {
        if (stopped) return;
        stopped = true;
        proc.kill('SIGTERM');
        await Promise.race([exited, sleep(5_000).then(() => proc.kill('SIGKILL'))]);
        chrome.close();
        fs.rmSync(profile, { recursive: true, force: true });
    };

    for (let attempt = 0; attempt < 100; attempt++) {
        if (proc.exitCode !== null) {
            await stop();
            throw new Error(`proxy exited during startup:\n${logs.join('\n')}`);
        }
        try {
            if ((await status()).chromeRunning) break;
        } catch { /* not listening yet */ }
        await sleep(100);
    }
    try {
        await chrome.waitFor((msg) => msg.method === 'Target.setAutoAttach');
    } catch (error) {
        await stop();
        throw new Error(`proxy never finished its boot handshake: ${error.message}\n${logs.join('\n')}`);
    }

    return {
        base,
        chrome,
        logs,
        status,
        stop,
        get: (route) => fetch(`${base}${route}`),
        /** True once the proxy logged a line containing `text`. */
        logged: (text) => logs.some((line) => line.includes(text)),
        async waitLogged(text, timeoutMs = WAIT_MS) {
            const deadline = Date.now() + timeoutMs;
            while (Date.now() < deadline) {
                if (logs.some((line) => line.includes(text))) return;
                await sleep(20);
            }
            throw new Error(`proxy never logged "${text}":\n${logs.join('\n')}`);
        },
        async connect() {
            const ws = new WebSocketClient(`ws://127.0.0.1:${port}`);
            await once(ws, 'open');
            return new CdpClient(ws);
        },
    };
}
