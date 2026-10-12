// Unit tests for session-router.mjs (pure routing logic, no Chrome needed).
// Run: node --test scripts/dev/chrome-agent/tests/
import test from 'node:test';
import assert from 'node:assert/strict';
import { SessionRouter } from '../session-router.mjs';

const ATTACHED = 'Target.attachedToTarget';
const DETACHED = 'Target.detachedFromTarget';

function setup() {
    const delivered = [];
    const detached = [];
    const logs = [];
    const router = new SessionRouter({
        deliver: (msg, to) => delivered.push({ msg, to }),
        detachSession: (sessionId) => detached.push(sessionId),
        log: (line) => logs.push(line),
    });
    const client = (id) => ({ id, label: `c${id}`, closed: false });
    return { router, delivered, detached, logs, client };
}

const info = (targetId, type = 'page') => ({ targetId, type, url: 'about:blank' });
const attached = (sessionId, targetId, extra = {}) => ({
    method: ATTACHED,
    params: { sessionId, targetInfo: info(targetId), waitingForDebugger: false },
    ...extra,
});
const detachedEvt = (sessionId, extra = {}) => ({ method: DETACHED, params: { sessionId }, ...extra });
const recipients = (delivered) => delivered.map((d) => (d.to === 'all' ? 'all' : d.to.label));

/** Drive the full client attach round-trip: forward → Chrome event → Chrome response. */
function attach(ctx, client, proxyId, targetId, sessionId, { eventFirst = true } = {}) {
    const req = { method: 'Target.attachToTarget', params: { targetId, flatten: true } };
    assert.equal(ctx.router.classifyClientRequest(client, req).action, 'forward');
    ctx.router.trackForwardedRequest(client, req, proxyId);
    if (eventFirst) ctx.router.onChromeEvent(attached(sessionId, targetId));
    ctx.router.onChromeResponse(proxyId, { id: proxyId, result: { sessionId } });
    if (!eventFirst) ctx.router.onChromeEvent(attached(sessionId, targetId));
}

test('base sessions are cached, broadcast and replayed to late clients', () => {
    const ctx = setup();
    ctx.router.onChromeEvent({ method: 'Target.targetCreated', params: { targetInfo: info('T1') } });
    ctx.router.onChromeEvent(attached('BASE1', 'T1'));
    assert.deepEqual(recipients(ctx.delivered), ['all', 'all']);
    assert.equal(ctx.router.knownSessions.size, 1);

    ctx.delivered.length = 0;
    const late = ctx.client(9);
    ctx.router.replayDiscovery(late);
    ctx.router.replayAutoAttach(late);
    assert.deepEqual(ctx.delivered.map((d) => d.msg.method), ['Target.targetCreated', ATTACHED]);
    assert.ok(ctx.delivered.every((d) => d.to === late));
});

for (const eventFirst of [true, false]) {
    test(`owned session reaches only its owner and is never cached (${eventFirst ? 'event' : 'response'} first)`, () => {
        const ctx = setup();
        const a = ctx.client(1);
        attach(ctx, a, 100, 'T1', 'OWN1', { eventFirst });
        assert.deepEqual(recipients(ctx.delivered), ['c1']);
        assert.equal(ctx.router.knownSessions.size, 0);

        ctx.delivered.length = 0;
        ctx.router.onChromeEvent({ method: 'Page.frameNavigated', sessionId: 'OWN1', params: {} });
        ctx.router.onChromeEvent(detachedEvt('OWN1'));
        assert.deepEqual(recipients(ctx.delivered), ['c1', 'c1']);
        assert.equal(ctx.router.owned.size, 0);
    });
}

test('late clients are not replayed other clients\' private sessions', () => {
    const ctx = setup();
    ctx.router.onChromeEvent(attached('BASE1', 'T1'));
    attach(ctx, ctx.client(1), 100, 'T1', 'OWN1');
    ctx.delivered.length = 0;
    ctx.router.replayAutoAttach(ctx.client(2));
    assert.deepEqual(ctx.delivered.map((d) => d.msg.params.sessionId), ['BASE1']);
});

test('concurrent attaches to one target are attributed to their own requesters', () => {
    const ctx = setup();
    const [a, b] = [ctx.client(1), ctx.client(2)];
    const req = (id) => ({ method: 'Target.attachToTarget', params: { targetId: 'T1' }, id });
    ctx.router.trackForwardedRequest(a, req(1), 100);
    ctx.router.trackForwardedRequest(b, req(2), 101);
    ctx.router.onChromeEvent(attached('SA', 'T1'));
    ctx.router.onChromeEvent(attached('SB', 'T1'));
    assert.equal(ctx.delivered.length, 0, 'both events held until responses name the sessions');
    ctx.router.onChromeResponse(101, { id: 101, result: { sessionId: 'SB' } });
    ctx.router.onChromeResponse(100, { id: 100, result: { sessionId: 'SA' } });
    assert.deepEqual(ctx.delivered.map((d) => [d.msg.params.sessionId, d.to.label]), [['SB', 'c2'], ['SA', 'c1']]);
    assert.equal(ctx.router.knownSessions.size, 0);
});

test('a base attach event racing an in-flight attachToTarget is released as base after the response', () => {
    const ctx = setup();
    const a = ctx.client(1);
    const req = { method: 'Target.attachToTarget', params: { targetId: 'T1' } };
    ctx.router.trackForwardedRequest(a, req, 100);
    ctx.router.onChromeEvent(attached('BASE1', 'T1'));
    ctx.router.onChromeEvent(attached('OWN1', 'T1'));
    ctx.router.onChromeResponse(100, { id: 100, result: { sessionId: 'OWN1' } });
    assert.deepEqual(ctx.delivered.map((d) => [d.msg.params.sessionId, d.to === 'all' ? 'all' : d.to.label]), [
        ['OWN1', 'c1'],
        ['BASE1', 'all'],
    ]);
    assert.deepEqual([...ctx.router.knownSessions.keys()], ['BASE1']);
});

test('held events are released as base when the attach request is abandoned or fails', () => {
    const ctx = setup();
    const a = ctx.client(1);
    const req = { method: 'Target.attachToTarget', params: { targetId: 'T1' } };
    ctx.router.trackForwardedRequest(a, req, 100);
    ctx.router.onChromeEvent(attached('BASE1', 'T1'));
    assert.equal(ctx.delivered.length, 0);
    ctx.router.onRequestAbandoned(100);
    assert.deepEqual(recipients(ctx.delivered), ['all']);

    ctx.router.trackForwardedRequest(a, req, 101);
    ctx.router.onChromeEvent(attached('BASE2', 'T1'));
    ctx.router.onChromeResponse(101, { id: 101, error: { message: 'no such target' } });
    assert.deepEqual(recipients(ctx.delivered), ['all', 'all']);
});

test('attachToBrowserTarget sessions are owned too', () => {
    const ctx = setup();
    const a = ctx.client(1);
    const req = { method: 'Target.attachToBrowserTarget', params: {} };
    ctx.router.trackForwardedRequest(a, req, 100);
    ctx.router.onChromeEvent({ method: ATTACHED, params: { sessionId: 'BR1', targetInfo: info('BROWSER', 'browser') } });
    ctx.router.onChromeResponse(100, { id: 100, result: { sessionId: 'BR1' } });
    assert.deepEqual(recipients(ctx.delivered), ['c1']);
});

test('detach: only the owner may detach; shared and foreign sessions are answered locally', () => {
    const ctx = setup();
    const [a, b] = [ctx.client(1), ctx.client(2)];
    ctx.router.onChromeEvent(attached('BASE1', 'T1'));
    attach(ctx, a, 100, 'T1', 'OWN1');
    const detach = (sessionId) => ({ method: 'Target.detachFromTarget', params: { sessionId } });

    assert.equal(ctx.router.classifyClientRequest(a, detach('OWN1')).action, 'forward');
    assert.deepEqual(ctx.router.classifyClientRequest(b, detach('OWN1')), { action: 'reply', result: {} });
    assert.deepEqual(ctx.router.classifyClientRequest(a, detach('BASE1')), { action: 'reply', result: {} });
    assert.deepEqual(ctx.router.classifyClientRequest(a, detach('NOPE')), { action: 'reply', result: {} });
    assert.ok(ctx.logs.some((l) => l.includes('c2 detach OWN1') && l.includes('owned by c1')));
    assert.ok(ctx.logs.some((l) => l.includes('c1 detach BASE1') && l.includes('shared base session')));
});

test('nested sessions inherit the owner; nested events never reach other clients', () => {
    const ctx = setup();
    attach(ctx, ctx.client(1), 100, 'T1', 'OWN1');
    ctx.delivered.length = 0;
    ctx.router.onChromeEvent({ ...attached('CHILD1', 'IFRAME1'), sessionId: 'OWN1' });
    ctx.router.onChromeEvent({ method: 'Runtime.executionContextCreated', sessionId: 'CHILD1', params: {} });
    ctx.router.onChromeEvent({ ...detachedEvt('CHILD1'), sessionId: 'OWN1' });
    assert.deepEqual(recipients(ctx.delivered), ['c1', 'c1', 'c1']);
    assert.equal(ctx.router.knownSessions.size, 0);
    assert.deepEqual([...ctx.router.owned.keys()], ['OWN1']);
});

test('nested sessions of a shared base session stay shared (cached, broadcast)', () => {
    const ctx = setup();
    ctx.router.onChromeEvent(attached('BASE1', 'T1'));
    ctx.router.onChromeEvent({ ...attached('BASECHILD', 'IFRAME1'), sessionId: 'BASE1' });
    assert.deepEqual(recipients(ctx.delivered), ['all', 'all']);
    assert.equal(ctx.router.knownSessions.size, 2);
});

test('client disconnect detaches its sessions and swallows the resulting events', () => {
    const ctx = setup();
    const a = ctx.client(1);
    attach(ctx, a, 100, 'T1', 'OWN1');
    attach(ctx, a, 101, 'T2', 'OWN2');
    ctx.router.onChromeEvent({ ...attached('CHILD1', 'IFRAME1'), sessionId: 'OWN1' });
    ctx.delivered.length = 0;

    a.closed = true;
    ctx.router.onClientClosed(a);
    assert.deepEqual(ctx.detached.sort(), ['OWN1', 'OWN2'], 'only top-level sessions are detached explicitly');

    ctx.router.onChromeEvent(detachedEvt('OWN1'));
    ctx.router.onChromeEvent(detachedEvt('OWN2'));
    assert.equal(ctx.delivered.length, 0, 'detach events of a departed client are never broadcast');
    assert.equal(ctx.router.owned.size, 0, 'subtree removed with its parent');
});

test('attach that completes after its client left is detached, not leaked', () => {
    const ctx = setup();
    const a = ctx.client(1);
    const req = { method: 'Target.attachToTarget', params: { targetId: 'T1' } };
    ctx.router.trackForwardedRequest(a, req, 100);
    a.closed = true;
    ctx.router.onClientClosed(a);
    ctx.router.onChromeEvent(attached('OWN1', 'T1'));
    ctx.router.onChromeResponse(100, { id: 100, result: { sessionId: 'OWN1' } });
    assert.deepEqual(ctx.detached, ['OWN1']);
    assert.equal(ctx.delivered.length, 0);
});

test('orphaned entries expire; reset clears everything', () => {
    const ctx = setup();
    const a = ctx.client(1);
    attach(ctx, a, 100, 'T1', 'OWN1');
    a.closed = true;
    ctx.router.onClientClosed(a);
    ctx.router.purgeOrphans(Date.now() + 29_000);
    assert.equal(ctx.router.owned.size, 1);
    ctx.router.purgeOrphans(Date.now() + 31_000);
    assert.equal(ctx.router.owned.size, 0);

    ctx.router.onChromeEvent(attached('BASE1', 'T1'));
    ctx.router.reset();
    assert.equal(ctx.router.knownSessions.size, 0);
    assert.equal(ctx.router.knownTargets.size, 0);
});

test('logRequest attributes navigations and tab closes to the connection', () => {
    const ctx = setup();
    const a = ctx.client(3);
    ctx.router.onChromeEvent(attached('BASE1', 'T1AAAAAAAAAA'));
    ctx.router.logRequest(a, { method: 'Page.navigate', sessionId: 'BASE1', params: { url: 'https://x.com/a' } });
    ctx.router.logRequest(a, { method: 'Target.closeTarget', params: { targetId: 'T9BBBBBBBBBB' } });
    ctx.router.logRequest(a, { method: 'Runtime.evaluate', sessionId: 'BASE1', params: {} });
    assert.deepEqual(ctx.logs, [
        'c3 Page.navigate target=T1AAAAAA url=https://x.com/a',
        'c3 Target.closeTarget target=T9BBBBBB',
    ]);
});
