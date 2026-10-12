// Unit tests for context-replay.mjs through SessionRouter (no Chrome needed).
// Run: node --test scripts/dev/chrome-agent/tests/
import test from 'node:test';
import assert from 'node:assert/strict';
import { SessionRouter } from '../session-router.mjs';

const CREATED = 'Runtime.executionContextCreated';

function setup() {
    const delivered = [];
    const router = new SessionRouter({
        deliver: (msg, to) => delivered.push({ msg, to }),
        detachSession: () => {},
        log: () => {},
    });
    const client = (id) => ({ id, label: `c${id}`, closed: false });
    router.onChromeEvent({
        method: 'Target.attachedToTarget',
        params: { sessionId: 'S', targetInfo: { targetId: 'T', type: 'page', url: 'about:blank' }, waitingForDebugger: false },
    });
    delivered.length = 0;
    return { router, delivered, client };
}

const context = (id) => ({ method: CREATED, sessionId: 'S', params: { context: { id, origin: 'http://x', name: '', auxData: { isDefault: id === 1 } } } });
const rpc = (router, client, proxyId, method, sessionId = 'S') => {
    router.trackForwardedRequest(client, { method, sessionId }, proxyId);
};
const toClient = (delivered, client) => delivered.filter((d) => d.to === client).map((d) => d.msg);

/** Chrome's behaviour for the first enable: contexts first, then the response. */
function firstEnable(ctx, client, proxyId, ids) {
    rpc(ctx.router, client, proxyId, 'Runtime.enable');
    for (const id of ids) ctx.router.onChromeEvent(context(id));
    ctx.router.onChromeResponse(proxyId, { id: proxyId, result: {} });
}

function lateEnable(ctx, client, proxyId) {
    rpc(ctx.router, client, proxyId, 'Runtime.enable');
    ctx.router.onChromeResponse(proxyId, { id: proxyId, result: {} });
}

test('the first enable is not echoed; a late enable gets the live contexts, only to itself', () => {
    const ctx = setup();
    const [a, b] = [ctx.client(1), ctx.client(2)];
    firstEnable(ctx, a, 1, [1, 2]);
    assert.deepEqual(toClient(ctx.delivered, a), [], 'no replay for the enabling client');
    assert.equal(ctx.delivered.filter((d) => d.to === 'all').length, 2, 'events are still broadcast');

    ctx.delivered.length = 0;
    lateEnable(ctx, b, 2);
    const replayed = toClient(ctx.delivered, b);
    assert.deepEqual(replayed.map((m) => m.params.context.id), [1, 2]);
    assert.ok(replayed.every((m) => m.method === CREATED && m.sessionId === 'S'));
    assert.equal(ctx.delivered.length, 2, 'nobody else receives the replay');
});

test('a navigation replaces the replayed set (cleared, destroyed, created)', () => {
    const ctx = setup();
    const [a, b] = [ctx.client(1), ctx.client(2)];
    firstEnable(ctx, a, 1, [1, 2, 3]);
    ctx.router.onChromeEvent({ method: 'Runtime.executionContextDestroyed', sessionId: 'S', params: { executionContextId: 2 } });
    lateEnable(ctx, b, 2);
    assert.deepEqual(toClient(ctx.delivered, b).map((m) => m.params.context.id), [1, 3]);

    ctx.delivered.length = 0;
    ctx.router.onChromeEvent({ method: 'Runtime.executionContextsCleared', sessionId: 'S', params: {} });
    ctx.router.onChromeEvent(context(7));
    const c = ctx.client(4);
    lateEnable(ctx, c, 4);
    assert.deepEqual(toClient(ctx.delivered, c).map((m) => m.params.context.id), [7]);
});

test('two enables in flight together are both first enables: events are broadcast, nothing is echoed', () => {
    const ctx = setup();
    const [a, b] = [ctx.client(1), ctx.client(2)];
    rpc(ctx.router, a, 1, 'Runtime.enable');
    rpc(ctx.router, b, 2, 'Runtime.enable');
    ctx.router.onChromeEvent(context(1));
    ctx.router.onChromeResponse(1, { id: 1, result: {} });
    ctx.router.onChromeResponse(2, { id: 2, result: {} });
    assert.deepEqual(toClient(ctx.delivered, a).concat(toClient(ctx.delivered, b)), []);
    assert.equal(ctx.delivered.filter((d) => d.to === 'all').length, 1);
});

test('Runtime.disable resets the session: the next enable is a first enable again', () => {
    const ctx = setup();
    const [a, b] = [ctx.client(1), ctx.client(2)];
    firstEnable(ctx, a, 1, [1]);
    rpc(ctx.router, a, 2, 'Runtime.disable');
    ctx.router.onChromeResponse(2, { id: 2, result: {} });
    ctx.delivered.length = 0;
    firstEnable(ctx, b, 3, [5]);
    assert.deepEqual(toClient(ctx.delivered, b), []);
});

test('an enable that Chrome rejects does not mark the session enabled', () => {
    const ctx = setup();
    const [a, b] = [ctx.client(1), ctx.client(2)];
    rpc(ctx.router, a, 1, 'Runtime.enable');
    ctx.router.onChromeResponse(1, { id: 1, error: { message: 'gone' } });
    firstEnable(ctx, b, 2, [1]);
    assert.deepEqual(toClient(ctx.delivered, b), []);
});

test('enabled state follows context events even if the enabling client left mid-request', () => {
    const ctx = setup();
    const [a, b] = [ctx.client(1), ctx.client(2)];
    rpc(ctx.router, a, 1, 'Runtime.enable');
    ctx.router.onChromeEvent(context(1));
    a.closed = true;
    ctx.router.onClientClosed(a);
    assert.equal(ctx.router.contextReplay.pending.size, 0, 'no leaked request');
    ctx.delivered.length = 0;
    lateEnable(ctx, b, 2);
    assert.deepEqual(toClient(ctx.delivered, b).map((m) => m.params.context.id), [1]);
});

test('private (owned) sessions are never replayed or cached', () => {
    const ctx = setup();
    const a = ctx.client(1);
    ctx.router.trackForwardedRequest(a, { method: 'Target.attachToTarget', params: { targetId: 'T' } }, 1);
    ctx.router.onChromeEvent({
        method: 'Target.attachedToTarget',
        params: { sessionId: 'P', targetInfo: { targetId: 'T', type: 'page', url: 'about:blank' } },
    });
    ctx.router.onChromeResponse(1, { id: 1, result: { sessionId: 'P' } });
    ctx.delivered.length = 0;
    lateEnable(ctx, a, 2);
    rpc(ctx.router, a, 3, 'Runtime.enable', 'P');
    ctx.router.onChromeEvent({ method: CREATED, sessionId: 'P', params: { context: { id: 9 } } });
    ctx.router.onChromeResponse(3, { id: 3, result: {} });
    assert.equal(ctx.router.contextReplay.contexts.has('P'), false);
    assert.equal(ctx.router.contextReplay.pending.size, 0);
});

test('a detached base session drops its contexts; browser-level requests are ignored', () => {
    const ctx = setup();
    firstEnable(ctx, ctx.client(1), 1, [1]);
    ctx.router.onChromeEvent({ method: 'Target.detachedFromTarget', params: { sessionId: 'S' } });
    assert.equal(ctx.router.contextReplay.contexts.has('S'), false);
    assert.equal(ctx.router.contextReplay.enabled.has('S'), false);
    ctx.router.trackForwardedRequest(ctx.client(2), { method: 'Runtime.enable' }, 9);
    assert.equal(ctx.router.contextReplay.pending.size, 0);
});

test('reset and abandoned requests leave nothing behind', () => {
    const ctx = setup();
    rpc(ctx.router, ctx.client(1), 1, 'Runtime.enable');
    ctx.router.onRequestAbandoned(1);
    assert.equal(ctx.router.contextReplay.pending.size, 0);
    firstEnable(ctx, ctx.client(1), 2, [1]);
    ctx.router.reset();
    assert.equal(ctx.router.contextReplay.contexts.size + ctx.router.contextReplay.enabled.size, 0);
});
