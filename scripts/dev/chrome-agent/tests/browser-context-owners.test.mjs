// Unit tests for browser-context-owners.mjs through the router that composes it (no Chrome needed).
// Run: node --test scripts/dev/chrome-agent/tests/
import test from 'node:test';
import assert from 'node:assert/strict';
import { createsBrowserContext } from '../browser-context-owners.mjs';
import { SessionRouter, outlivesClient } from '../session-router.mjs';

function setup() {
    const disposed = [];
    const logs = [];
    const router = new SessionRouter({
        deliver: () => {},
        detachSession: () => {},
        disposeBrowserContext: (browserContextId) => disposed.push(browserContextId),
        log: (line) => logs.push(line),
    });
    const client = (id) => ({ id, label: `c${id}`, closed: false });
    /** The proxy marks a client closed before telling the router. */
    const disconnect = (who) => {
        who.closed = true;
        router.onClientClosed(who);
    };
    return { router, disposed, logs, client, disconnect };
}

const CREATE = { method: 'Target.createBrowserContext', params: {} };
const disposeRequest = (browserContextId) => ({ method: 'Target.disposeBrowserContext', params: { browserContextId } });

/** Forward a creation request under `proxyId` and let Chrome answer it with `browserContextId`. */
function create(ctx, client, proxyId, browserContextId) {
    ctx.router.trackForwardedRequest(client, CREATE, proxyId);
    ctx.router.onChromeResponse(proxyId, { id: proxyId, result: { browserContextId } });
}

test('a client that disconnects takes its contexts with it, and only its own', () => {
    const ctx = setup();
    const [a, b] = [ctx.client(1), ctx.client(2)];
    create(ctx, a, 10, 'CTX-A1');
    create(ctx, a, 11, 'CTX-A2');
    create(ctx, b, 12, 'CTX-B1');
    assert.equal(ctx.router.browserContexts.size, 3);
    assert.deepEqual(ctx.disposed, []);

    ctx.disconnect(a);
    assert.deepEqual(ctx.disposed, ['CTX-A1', 'CTX-A2']);
    assert.equal(ctx.router.browserContexts.size, 1);
    assert.ok(ctx.logs.includes('c1 disconnected: disposing 2 owned browser context(s)'));

    ctx.disconnect(b);
    assert.deepEqual(ctx.disposed, ['CTX-A1', 'CTX-A2', 'CTX-B1']);
    assert.equal(ctx.router.browserContexts.size, 0);
});

test('a context is never disposed while its creator is connected', () => {
    const ctx = setup();
    const [a, b] = [ctx.client(1), ctx.client(2)];
    create(ctx, a, 10, 'CTX-A1');
    ctx.disconnect(b);
    assert.deepEqual(ctx.disposed, []);
    assert.equal(ctx.router.browserContexts.size, 1);
});

test('creation is attributed to the creating connection in the log', () => {
    const ctx = setup();
    create(ctx, ctx.client(3), 10, 'CTX-1');
    assert.deepEqual(ctx.logs, ['c3 create browser context CTX-1 (owned)']);
});

test('a context its creator disposed itself is not disposed again on disconnect', () => {
    const ctx = setup();
    const a = ctx.client(1);
    create(ctx, a, 10, 'CTX-A1');
    create(ctx, a, 11, 'CTX-A2');
    ctx.router.trackForwardedRequest(a, disposeRequest('CTX-A1'), 12);
    assert.equal(ctx.router.browserContexts.size, 1);

    ctx.disconnect(a);
    assert.deepEqual(ctx.disposed, ['CTX-A2']);
});

test('a dispose request releases the context whoever sent it: Chrome disposes whichever id it is given', () => {
    const ctx = setup();
    const [a, b] = [ctx.client(1), ctx.client(2)];
    create(ctx, a, 10, 'CTX-A1');
    ctx.router.trackForwardedRequest(b, disposeRequest('CTX-A1'), 11);
    ctx.disconnect(a);
    assert.deepEqual(ctx.disposed, []);
});

test('an answer that reaches the proxy after its client left is disposed on arrival, never adopted', () => {
    const ctx = setup();
    const a = ctx.client(1);
    ctx.router.trackForwardedRequest(a, CREATE, 10);
    ctx.disconnect(a);
    assert.deepEqual(ctx.disposed, []);

    ctx.router.onChromeResponse(10, { id: 10, result: { browserContextId: 'CTX-LATE' } });
    assert.deepEqual(ctx.disposed, ['CTX-LATE']);
    assert.equal(ctx.router.browserContexts.size, 0);
    assert.ok(ctx.logs.includes('c1 left while creating browser context CTX-LATE: disposing it'));
});

test('a late answer is disposed once: a second answer for the same request does nothing', () => {
    const ctx = setup();
    const a = ctx.client(1);
    ctx.router.trackForwardedRequest(a, CREATE, 10);
    ctx.disconnect(a);
    ctx.router.onChromeResponse(10, { id: 10, result: { browserContextId: 'CTX-LATE' } });
    ctx.router.onChromeResponse(10, { id: 10, result: { browserContextId: 'CTX-LATE' } });
    assert.deepEqual(ctx.disposed, ['CTX-LATE']);
});

test('a refused or id-less creation owns nothing and disposes nothing', () => {
    const ctx = setup();
    const a = ctx.client(1);
    ctx.router.trackForwardedRequest(a, CREATE, 10);
    ctx.router.onChromeResponse(10, { id: 10, error: { code: -32000, message: 'refused' } });
    ctx.router.trackForwardedRequest(a, CREATE, 11);
    ctx.router.onChromeResponse(11, { id: 11, result: {} });
    assert.equal(ctx.router.browserContexts.size, 0);

    ctx.disconnect(a);
    assert.deepEqual(ctx.disposed, []);
});

test('only creation requests establish ownership', () => {
    const ctx = setup();
    const a = ctx.client(1);
    const createTarget = { method: 'Target.createTarget', params: { url: 'about:blank' } };
    ctx.router.trackForwardedRequest(a, createTarget, 10);
    ctx.router.onChromeResponse(10, { id: 10, result: { targetId: 'T1', browserContextId: 'CTX-DEFAULT' } });
    ctx.router.onChromeResponse(11, { id: 11, result: { browserContextId: 'CTX-UNTRACKED' } });
    assert.equal(ctx.router.browserContexts.size, 0);

    ctx.disconnect(a);
    assert.deepEqual(ctx.disposed, []);
});

test('an abandoned creation request is forgotten: a later answer is ignored', () => {
    const ctx = setup();
    const a = ctx.client(1);
    ctx.router.trackForwardedRequest(a, CREATE, 10);
    ctx.router.onRequestAbandoned(10);
    ctx.disconnect(a);
    ctx.router.onChromeResponse(10, { id: 10, result: { browserContextId: 'CTX-GONE' } });
    assert.deepEqual(ctx.disposed, []);
    assert.equal(ctx.router.browserContexts.size, 0);
});

test('a Chrome restart forgets every context and every unanswered creation', () => {
    const ctx = setup();
    const [a, b] = [ctx.client(1), ctx.client(2)];
    create(ctx, a, 10, 'CTX-A1');
    ctx.router.trackForwardedRequest(b, CREATE, 11);

    ctx.router.reset();
    assert.equal(ctx.router.browserContexts.size, 0);

    ctx.disconnect(a);
    ctx.disconnect(b);
    ctx.router.onChromeResponse(11, { id: 11, result: { browserContextId: 'CTX-STALE' } });
    assert.deepEqual(ctx.disposed, []);
});

test('only attach and context-creation requests outlive their client', () => {
    for (const method of ['Target.attachToTarget', 'Target.attachToBrowserTarget', 'Target.createBrowserContext']) {
        assert.equal(outlivesClient(method), true, method);
    }
    for (const method of ['Target.disposeBrowserContext', 'Target.createTarget', 'Page.navigate', undefined]) {
        assert.equal(outlivesClient(method), false, String(method));
    }
    assert.equal(createsBrowserContext('Target.createBrowserContext'), true);
    assert.equal(createsBrowserContext('Target.disposeBrowserContext'), false);
});
