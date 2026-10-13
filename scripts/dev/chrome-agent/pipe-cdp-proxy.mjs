#!/usr/bin/env node
/**
 * pipe-cdp-proxy — multi-client WebSocket front for a single pipe-connected Chrome
 *
 * Lets multiple chrome-devtools-mcp instances (one per Claude Code session) share
 * one Chrome instance via --browserUrl. CDP traffic to Chrome flows over stdio
 * pipes (--remote-debugging-pipe), bypassing the macOS NSApplication-activation
 * bug that affects WebSocket-CDP transport (chrome-devtools-mcp#1254).
 *
 * Architecture:
 *
 *   [MCP-A] ─┐
 *   [MCP-B] ─┼── WebSocket(localhost:9410) ── Pipe Multiplexer ── stdio ── [Chrome]
 *   [MCP-C] ─┘
 *
 * Session model (see session-router.mjs):
 *   - The proxy itself enables Target discovery + auto-attach with Chrome on boot.
 *     Those "base" sessions are shared: cached, replayed to late clients (a client's
 *     Target.setDiscoverTargets / setAutoAttach is answered from the cache instead of
 *     being forwarded, since Chrome would treat it as a no-op), events broadcast.
 *   - Sessions a client creates itself (Target.attachToTarget) are private to it:
 *     other clients never see their attach/detach, cannot detach them, and the proxy
 *     detaches them when the owner disconnects.
 *
 * Observability: every connection has an id (`c1`, `c2`, …); connects, disconnects, private session
 * attach/detach, blocked detaches, navigations/tab closes and requests Chrome leaves unanswered for 10 s
 * (request-watch.mjs) are logged with timestamps and that id, so a lost or hung page can be attributed.
 * A page that stays silent after a request on it timed out (60 s) is closed (hang-guard.mjs), so a hung
 * renderer cannot hold a session for longer than about two minutes.
 */

import { spawn } from 'child_process';
import { WebSocketServer, WebSocket } from 'ws';
import { buildChromeLaunchArgs, resetProfileCrashFlags } from './chrome-launch.mjs';
import { startHangGuard } from './hang-guard.mjs';
import { createHttpServer } from './http-endpoints.mjs';
import { startIdlePool } from './idle-pool.mjs';
import { describeScript, startRequestWatch } from './request-watch.mjs';
import { SessionRouter, isAttachMethod, short } from './session-router.mjs';
import { createProxyStallForensics } from './stall-probe.mjs';

const args = process.argv.slice(2);
const getArg = (name, def) => {
    const i = args.indexOf(name);
    return i >= 0 ? args[i + 1] : def;
};

const PROXY_PORT = parseInt(getArg('--port', '9410'));
const CHROME_PATH = getArg(
    '--chrome-path',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
);
const USER_DATA_DIR = getArg(
    '--user-data-dir',
    `${process.env.HOME}/Library/Application Support/Chrome-Pipe-Proxy`
);
const INITIAL_URL = getArg('--initial-url', 'about:blank');
const FOREGROUND = process.env.MYRM_CHROME_AGENT_FOREGROUND === '1';
const ALLOW_E2E_URLS = process.env.MYRM_CHROME_AGENT_ALLOW_E2E_URLS === '1';

const E2E_URL_REJECT_MESSAGE =
    'CHROME_AGENT_E2E_URL_REJECTED: ChromeAgent :9410 is for Agent tasks (e.g. URL extraction) only; '
    + 'chrome_e2e must use ./myrm test harness → ChromeE2E :9333';

/** Block localhost UI URLs that belong on ChromeE2E :9333, not ChromeAgent :9410. */
function isForbiddenE2eUrl(rawUrl) {
    if (ALLOW_E2E_URLS || typeof rawUrl !== 'string' || !rawUrl.trim()) {
        return false;
    }
    let parsed;
    try {
        parsed = new URL(rawUrl);
    } catch (_) {
        return false;
    }
    const host = parsed.hostname.toLowerCase();
    if (host !== '127.0.0.1' && host !== 'localhost') {
        return false;
    }
    const port = parsed.port || (parsed.protocol === 'https:' ? '443' : '80');
    return port === '3000' || port === '3002';
}

function navigateUrlFromCdpMethod(msg) {
    if (msg.method === 'Page.navigate' || msg.method === 'Target.createTarget') {
        return msg.params?.url;
    }
    return undefined;
}

function rejectE2eUrlToClient(clientWs, msg, rawUrl) {
    if (msg.id === undefined) {
        return;
    }
    log(`Rejected E2E URL on ChromeAgent (${msg.method}): ${rawUrl}`);
    safeSend(clientWs, {
        id: msg.id,
        error: { code: -32001, message: E2E_URL_REJECT_MESSAGE },
    });
}

const log = (line) => console.log(`${new Date().toISOString()} [Proxy] ${line}`);
const logError = (line, ...rest) => console.error(`${new Date().toISOString()} [Proxy] ${line}`, ...rest);

// Set PROXY_DEBUG=1 in the env to trace every CDP message. Off by default
// because chatty traffic (Page.*, Runtime.*) drowns the log.
const DEBUG = process.env.PROXY_DEBUG === '1';
const dbg = (...rest) => DEBUG && console.log('[Proxy.dbg]', ...rest);

// ═══════════════════════════════════════════
// Chrome process management
// ═══════════════════════════════════════════

let chromeProcess = null;
let chromeWritable = null;     // fd 3: parent → Chrome
let chromeReadable = null;     // fd 4: Chrome → parent
let chromeBuffer = Buffer.alloc(0);
let restartTimer = null;
let chromeLaunchedAt = 0;

function launchChrome() {
    if (chromeProcess) return;
    log(`Launching Chrome (--user-data-dir=${USER_DATA_DIR})`);
    resetProfileCrashFlags(USER_DATA_DIR);
    const chromeArgs = buildChromeLaunchArgs({
        userDataDir: USER_DATA_DIR,
        initialUrl: INITIAL_URL,
        foreground: FOREGROUND,
    });

    chromeProcess = spawn(CHROME_PATH, chromeArgs, {
        stdio: ['ignore', 'ignore', 'inherit', 'pipe', 'pipe'],
    });
    chromeWritable = chromeProcess.stdio[3];
    chromeReadable = chromeProcess.stdio[4];

    chromeReadable.on('data', handleChromeData);
    chromeReadable.on('error', (err) => logError('Chrome read error:', err.message));

    const launchedAt = chromeLaunchedAt = Date.now();
    chromeProcess.on('exit', (code, signal) => {
        const lifetime = Date.now() - launchedAt;
        logError(`Chrome exited (code=${code}, signal=${signal}, lived ${lifetime}ms)`);
        const wasRunning = chromeProcess !== null;
        chromeProcess = null;
        chromeWritable = null;
        chromeReadable = null;
        chromeBuffer = Buffer.alloc(0);
        router.reset();
        for (const [, req] of pendingRequests) {
            safeSend(req.clientWs, {
                id: req.originalId,
                error: { code: -32000, message: 'Chrome exited' },
            });
        }
        pendingRequests.clear();
        // Don't auto-restart Chrome that died too fast — it's a config error,
        // not a transient failure. Looping would spam windows / processes.
        if (lifetime < 3000) {
            logError('Chrome died too fast; not auto-restarting (likely a launch-flag/profile error)');
            return;
        }
        if (wasRunning && !restartTimer) {
            restartTimer = setTimeout(() => {
                restartTimer = null;
                launchChrome();
                // Give Chrome a beat to come up before re-enabling discovery.
                setTimeout(() => enableProxyDiscovery().catch((e) =>
                    logError('Failed to re-enable discovery after restart:', e.message)
                ), 500);
            }, 2000);
        }
    });

    chromeProcess.on('error', (err) => logError('Chrome spawn error:', err.message));
}

function handleChromeData(chunk) {
    chromeBuffer = Buffer.concat([chromeBuffer, chunk]);
    let nullIdx;
    while ((nullIdx = chromeBuffer.indexOf(0)) !== -1) {
        const msgBuf = chromeBuffer.subarray(0, nullIdx);
        chromeBuffer = chromeBuffer.subarray(nullIdx + 1);
        if (msgBuf.length === 0) continue;
        try {
            routeChromeMessage(JSON.parse(msgBuf.toString('utf-8')));
        } catch (e) {
            logError('Failed to parse Chrome message:', e.message);
        }
    }
}

function sendToChrome(msg) {
    if (!chromeWritable) return false;
    chromeWritable.write(JSON.stringify(msg) + '\0');
    return true;
}

// ═══════════════════════════════════════════
// Clients, pending requests, routing
// ═══════════════════════════════════════════

let globalIdCounter = 1;
let clientCounter = 0;
const pendingRequests = new Map();   // proxyId → { clientWs, client, originalId, method, sessionId, awaitsScript, script, createdAt }
const clients = new Map();           // ws → { id, label, ws, closed, proxyIds, connectedAt, discoveryEnabled, autoAttachEnabled }

function safeSend(ws, data) {
    if (!ws) return;
    if (typeof ws.send !== 'function') return;
    if (ws.readyState !== undefined && ws.readyState !== WebSocket.OPEN) return;
    ws.send(typeof data === 'string' ? data : JSON.stringify(data));
}

const router = new SessionRouter({
    deliver(msg, to) {
        if (to === 'all') {
            const payload = JSON.stringify(msg);
            for (const [ws] of clients) safeSend(ws, payload);
        } else {
            safeSend(to.ws, msg);
        }
    },
    detachSession(sessionId) {
        cdpRequest('Target.detachFromTarget', { sessionId }).catch((e) =>
            logError(`detach of orphaned session ${short(sessionId)} failed:`, e.message)
        );
    },
    log,
});

function routeChromeMessage(msg) {
    if (DEBUG) {
        const summary = msg.method
            ? `EVENT ${msg.method}${msg.sessionId ? ' sess=' + msg.sessionId.substring(0, 8) : ''}`
            : `RESP id=${msg.id}${msg.sessionId ? ' sess=' + msg.sessionId.substring(0, 8) : ''}${msg.error ? ' ERR=' + msg.error.message : ''}`;
        dbg('← Chrome', summary);
    }

    // Response: route by id back to the originating client.
    if (msg.id !== undefined && pendingRequests.has(msg.id)) {
        const proxyId = msg.id;
        const { clientWs, client, originalId } = pendingRequests.get(proxyId);
        pendingRequests.delete(proxyId);
        client?.proxyIds.delete(proxyId);
        router.onChromeResponse(proxyId, msg);
        msg.id = originalId;
        safeSend(clientWs, msg);
        return;
    }

    if (msg.method) {
        router.onChromeEvent(msg);
    }
}

// ═══════════════════════════════════════════
// Internal CDP request (proxy-initiated: discovery setup, HTTP endpoints, idle pool, hang guard)
// ═══════════════════════════════════════════

function cdpRequest(method, params = {}, { sessionId, timeoutMs = 5000 } = {}) {
    return new Promise((resolve, reject) => {
        if (!chromeWritable) return reject(new Error('Chrome not running'));
        const proxyId = globalIdCounter++;
        const timeout = setTimeout(() => {
            pendingRequests.delete(proxyId);
            reject(Object.assign(new Error(`CDP request '${method}' timed out`), { timedOut: true }));
        }, timeoutMs);
        const fakeClient = {
            send: (data) => {
                clearTimeout(timeout);
                resolve(typeof data === 'string' ? JSON.parse(data) : data);
            },
            readyState: WebSocket.OPEN,
        };
        pendingRequests.set(proxyId, {
            clientWs: fakeClient,
            client: null,
            originalId: proxyId,
            method,
            createdAt: Date.now(),
        });
        sendToChrome({ id: proxyId, method, params, sessionId });
    });
}

// On Chrome boot/restart: enable discovery + auto-attach so the proxy receives
// (and caches) every Target.* event, even before any real clients connect.
// Chrome via --remote-debugging-pipe can take well over 500ms to accept CDP;
// retry instead of giving up, otherwise the cache stays empty and every
// client sees "No page selected".
async function enableProxyDiscovery(retries = 10) {
    if (!chromeWritable) return;
    for (let attempt = 1; attempt <= retries; attempt++) {
        try {
            await cdpRequest('Target.setDiscoverTargets', { discover: true });
            await cdpRequest('Target.setAutoAttach', {
                autoAttach: true,
                waitForDebuggerOnStart: false,
                flatten: true,
            });
            log('Discovery + auto-attach enabled by proxy itself');
            return;
        } catch (e) {
            if (attempt === retries) {
                logError(`Discovery enable failed after ${retries} attempts: ${e.message}`);
                return;
            }
            await new Promise((resolve) => setTimeout(resolve, 1000));
        }
    }
}

// ═══════════════════════════════════════════
// HTTP discovery endpoints
// ═══════════════════════════════════════════

function proxyStatus() {
    return {
        chromeRunning: chromeProcess !== null,
        chromePid: chromeProcess?.pid || null,
        clients: clients.size,
        knownTargets: router.knownTargets.size,
        knownSessions: router.knownSessions.size,
        pendingRequests: pendingRequests.size,
        ownedSessions: router.owned.size,
        leasedTabs: router.tabLease.leases.size,
        connections: [...clients.values()].map((c) => ({
            id: c.label,
            connectedAt: new Date(c.connectedAt).toISOString(),
            ownedSessions: router.ownedCountOf(c),
        })),
    };
}

const idlePool = startIdlePool({ cdpRequest, log, chromeUp: () => Boolean(chromeWritable), lease: router.tabLease });
const chromeAgeMs = () => (chromeProcess ? Date.now() - chromeLaunchedAt : null);
const stallForensics = createProxyStallForensics({ pendingRequests, router, cdpRequest, log, chromePid: () => chromeProcess?.pid });
const requestWatch = startRequestWatch({ pendingRequests, log, chromeAgeMs, describeSession: (id) => router.describeSession(id), stallSnapshot: stallForensics });
const hangGuard = startHangGuard({ pendingRequests, router, safeSend, cdpRequest, log, chromeAgeMs });
const server = createHttpServer({
    port: PROXY_PORT,
    chromeUp: () => Boolean(chromeWritable),
    cdpRequest,
    status: () => ({ ...proxyStatus(), ...requestWatch.stats(), ...idlePool.stats(), ...hangGuard.stats() }),
    isForbiddenUrl: isForbiddenE2eUrl,
    forbiddenUrlMessage: E2E_URL_REJECT_MESSAGE,
});

// ═══════════════════════════════════════════
// WebSocket server (CDP traffic from MCP clients)
// ═══════════════════════════════════════════

const wss = new WebSocketServer({ server });

wss.on('connection', (clientWs) => {
    const id = ++clientCounter;
    const client = {
        id,
        label: `c${id}`,
        ws: clientWs,
        closed: false,
        proxyIds: new Set(),
        connectedAt: Date.now(),
        discoveryEnabled: false,
        autoAttachEnabled: false,
    };
    clients.set(clientWs, client);
    log(`${client.label} connected (total: ${clients.size})`);

    clientWs.on('message', (data) => {
        if (!chromeWritable) {
            try {
                const msg = JSON.parse(data.toString());
                if (msg.id !== undefined) {
                    safeSend(clientWs, {
                        id: msg.id,
                        error: { code: -1, message: 'Chrome not running' },
                    });
                }
            } catch (_) { /* ignore */ }
            return;
        }

        let msg;
        try {
            msg = JSON.parse(data.toString());
        } catch (e) {
            logError(`${client.label} bad message:`, e.message);
            return;
        }

        // Intercept browser-level (no sessionId) discovery + auto-attach so the
        // client sees the cached base state. Forwarding to Chrome would be a no-op
        // (the proxy itself already enabled both). Per-session calls (sessionId set)
        // are session-scoped (e.g., iframe auto-attach within a target) and must be
        // forwarded normally — intercepting them caused infinite replay loops.
        if (msg.method === 'Target.setDiscoverTargets' && !msg.sessionId) {
            client.discoveryEnabled = msg.params?.discover === true;
            // Match Chrome's ordering: emit initial targetCreated events first,
            // then respond. Puppeteer captures the events then resolves on response.
            if (client.discoveryEnabled) router.replayDiscovery(client);
            if (msg.id !== undefined) safeSend(clientWs, { id: msg.id, result: {} });
            return;
        }
        if (msg.method === 'Target.setAutoAttach' && !msg.sessionId) {
            client.autoAttachEnabled = msg.params?.autoAttach === true;
            if (client.autoAttachEnabled) router.replayAutoAttach(client);
            if (msg.id !== undefined) safeSend(clientWs, { id: msg.id, result: {} });
            return;
        }

        const navigateUrl = navigateUrlFromCdpMethod(msg);
        if (isForbiddenE2eUrl(navigateUrl)) {
            rejectE2eUrlToClient(clientWs, msg, navigateUrl);
            return;
        }

        const decision = router.classifyClientRequest(client, msg);
        if (decision.action === 'reply') {
            if (msg.id !== undefined) safeSend(clientWs, { id: msg.id, result: decision.result, error: decision.error });
            return;
        }

        router.logRequest(client, msg);

        // ID remap so multiple clients don't collide on Chrome's request IDs.
        const origId = msg.id;
        if (msg.id !== undefined) {
            const proxyId = globalIdCounter++;
            pendingRequests.set(proxyId, {
                clientWs,
                client,
                originalId: msg.id,
                method: msg.method, sessionId: msg.sessionId,
                awaitsScript: msg.params?.awaitPromise === true,
                script: describeScript(msg.params),
                createdAt: Date.now(),
            });
            client.proxyIds.add(proxyId);
            router.trackForwardedRequest(client, msg, proxyId, decision);
            if (decision.acquiredLease) idlePool.reconcile();
            msg.id = proxyId;
        }

        dbg('→ Chrome', `${msg.method}${msg.sessionId ? ' sess=' + msg.sessionId.substring(0, 8) : ''} (cid=${origId} pid=${msg.id})`);
        sendToChrome(msg);
    });

    const cleanup = () => {
        if (client.closed) return;
        client.closed = true;
        // Attach requests stay pending: if Chrome still answers, the new session
        // has an owner who is gone and must be detached, not leaked.
        for (const pid of client.proxyIds) {
            if (!isAttachMethod(pendingRequests.get(pid)?.method)) pendingRequests.delete(pid);
        }
        clients.delete(clientWs);
        log(`${client.label} disconnected (remaining: ${clients.size})`);
        router.onClientClosed(client);
    };

    clientWs.on('close', cleanup);
    clientWs.on('error', cleanup);
});

// ═══════════════════════════════════════════
// Lifecycle
// ═══════════════════════════════════════════

process.on('uncaughtException', (err) => logError('Uncaught exception:', err.message, err.stack));
process.on('unhandledRejection', (reason) => logError('Unhandled rejection:', reason));
// Stay alive when launched via nohup / background shell (macOS SIGHUP).
process.on('SIGHUP', () => log('Ignoring SIGHUP (daemon mode)'));

function shutdown() {
    log('Shutting down');
    try { chromeProcess?.kill('SIGTERM'); } catch (_) {}
    process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

server.listen(PROXY_PORT, '127.0.0.1', () => {
    log(`Listening on http://127.0.0.1:${PROXY_PORT}`);
    launchChrome();
    // Wait a beat for Chrome to come up before enabling discovery.
    setTimeout(() => enableProxyDiscovery().catch((e) =>
        logError('Failed to enable discovery on boot:', e.message)
    ), 500);
});
