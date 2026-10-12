// Unit tests for tab-lease.mjs and its wiring in session-router.mjs (no Chrome needed).
// Run: node --test scripts/dev/chrome-agent/tests/tab-lease.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { TabLease } from '../tab-lease.mjs';
import { SessionRouter } from '../session-router.mjs';

const T = 'TARGET-AAAAAAAA';
const navigate = (url) => ({ method: 'Page.navigate', params: { url } });
const client = (label) => ({ label, closed: false });

function setup() {
    const urls = new Map();
    const logs = [];
    let clock = 1_000_000;
    const lease = new TabLease({ urlOf: (id) => urls.get(id), log: (l) => logs.push(l), now: () => clock });
    return { lease, urls, logs, advance: (ms) => { clock += ms; } };
}

test('first navigator leases the tab, second is rejected with an instruction', () => {
    const { lease } = setup();
    const [a, b] = [client('c1'), client('c2')];
    assert.deepEqual(lease.guard(a, T, navigate('https://x.com/a')), { acquired: T });
    const verdict = lease.guard(b, T, navigate('https://x.com/b'));
    assert.match(verdict.rejected, /TAB_LEASED.*list_pages.*NO_IDLE_TAB/s);
    assert.equal(verdict.acquired, undefined);
});

test('lessee may navigate again; releasing with about:blank frees the tab for others', () => {
    const { lease } = setup();
    const [a, b] = [client('c1'), client('c2')];
    lease.guard(a, T, navigate('https://x.com/a'));
    assert.deepEqual(lease.guard(a, T, navigate('https://x.com/a/ref')), {});
    assert.deepEqual(lease.guard(a, T, navigate('about:blank')), {});
    assert.deepEqual(lease.guard(b, T, navigate('https://x.com/b')), { acquired: T });
});

test('a foreign about:blank navigation cannot release someone else\'s tab', () => {
    const { lease } = setup();
    const [a, b] = [client('c1'), client('c2')];
    lease.guard(a, T, navigate('https://x.com/a'));
    assert.ok(lease.guard(b, T, navigate('about:blank')).rejected);
    assert.ok(lease.guard(a, T, navigate('https://x.com/a2')).rejected === undefined);
});

test('reload and history navigation are guarded, other methods are not', () => {
    const { lease } = setup();
    const [a, b] = [client('c1'), client('c2')];
    lease.guard(a, T, navigate('https://x.com/a'));
    assert.ok(lease.guard(b, T, { method: 'Page.reload', params: {} }).rejected);
    assert.ok(lease.guard(b, T, { method: 'Page.navigateToHistoryEntry', params: { entryId: 1 } }).rejected);
    assert.deepEqual(lease.guard(b, T, { method: 'Runtime.evaluate', params: { expression: '1' } }), {});
});

test('reload on an unleased tab never creates a lease', () => {
    const { lease } = setup();
    assert.deepEqual(lease.guard(client('c1'), T, { method: 'Page.reload', params: {} }), {});
    assert.equal(lease.leases.size, 0);
});

test('navigating an idle tab to about:blank is a no-op, not a lease', () => {
    const { lease } = setup();
    assert.deepEqual(lease.guard(client('c1'), T, navigate('about:blank')), {});
    assert.equal(lease.leases.size, 0);
});

test('a disconnecting or closed lessee frees its tabs', () => {
    const { lease } = setup();
    const [a, b] = [client('c1'), client('c2')];
    lease.guard(a, T, navigate('https://x.com/a'));
    lease.onClientClosed(a);
    assert.deepEqual(lease.guard(b, T, navigate('https://x.com/b')), { acquired: T });

    const c = client('c3');
    lease.guard(c, 'OTHER-BBBBBBBB', navigate('https://x.com/c'));
    c.closed = true;
    assert.deepEqual(lease.guard(b, 'OTHER-BBBBBBBB', navigate('https://x.com/d')), { acquired: 'OTHER-BBBBBBBB' });
});

test('a lease whose tab never left about:blank is reclaimed after 60s, a loaded tab never is', () => {
    const { lease, urls, advance } = setup();
    const [a, b] = [client('c1'), client('c2')];
    lease.guard(a, T, navigate('https://x.com/a'));
    urls.set(T, 'about:blank');
    advance(59_000);
    assert.ok(lease.guard(b, T, navigate('https://x.com/b')).rejected);
    advance(2_000);
    assert.deepEqual(lease.guard(b, T, navigate('https://x.com/b')), { acquired: T });

    lease.guard(a, 'LOADED-CCCCCCCC', navigate('https://x.com/a'));
    urls.set('LOADED-CCCCCCCC', 'https://x.com/a');
    advance(3_600_000);
    assert.ok(lease.guard(b, 'LOADED-CCCCCCCC', navigate('https://x.com/b')).rejected);
});

test('revoke only undoes the lease the refused request acquired', () => {
    const { lease } = setup();
    const [a, b] = [client('c1'), client('c2')];
    lease.guard(a, T, navigate('https://x.com/a'));
    lease.revoke(T, b);
    assert.equal(lease.leases.size, 1);
    lease.revoke(T, a);
    assert.equal(lease.leases.size, 0);
});

test('a lessee that leaves a loaded tab behind abandons it; a released or blank tab is not abandoned', () => {
    const { lease, urls, advance } = setup();
    const a = client('c1');
    lease.guard(a, T, navigate('https://x.com/a'));
    urls.set(T, 'https://x.com/a');
    lease.guard(a, 'BLANKED-DDDDDDDD', navigate('https://x.com/b'));
    urls.set('BLANKED-DDDDDDDD', 'about:blank');
    lease.onClientClosed(a);
    assert.deepEqual([...lease.abandoned.keys()], [T]);
    advance(599_000);
    assert.deepEqual(lease.takeAbandoned(600_000), []);
    advance(2_000);
    assert.deepEqual(lease.takeAbandoned(600_000), [T]);
    assert.deepEqual(lease.takeAbandoned(600_000), []);
});

test('a new lease, a release to about:blank, or tab destruction cancels the abandonment', () => {
    const { lease, urls } = setup();
    const [a, b] = [client('c1'), client('c2')];
    for (const id of ['T1-AAAAAAAA', 'T2-BBBBBBBB', 'T3-CCCCCCCC']) {
        lease.guard(a, id, navigate('https://x.com/a'));
        urls.set(id, 'https://x.com/a');
    }
    lease.onClientClosed(a);
    assert.equal(lease.abandoned.size, 3);
    lease.guard(b, 'T1-AAAAAAAA', navigate('https://x.com/new'));
    lease.guard(b, 'T2-BBBBBBBB', navigate('about:blank'));
    lease.forget('T3-CCCCCCCC');
    assert.equal(lease.abandoned.size, 0);
});

test('reset forgets abandoned tabs too', () => {
    const { lease, urls } = setup();
    const a = client('c1');
    lease.guard(a, T, navigate('https://x.com/a'));
    urls.set(T, 'https://x.com/a');
    lease.onClientClosed(a);
    lease.reset();
    assert.equal(lease.abandoned.size, 0);
});

// ── wiring inside the router ────────────────────────────────────────

function routerSetup() {
    const router = new SessionRouter({ deliver() {}, detachSession() {}, log() {} });
    const [a, b] = [client('c1'), client('c2')];
    // Owned sessions bound to the same target, as a real attachToTarget would create.
    router.owned.set('SESS-A', { owner: a, targetId: T, parent: null, orphanedAt: null });
    router.owned.set('SESS-B', { owner: b, targetId: T, parent: null, orphanedAt: null });
    const nav = (sessionId, url) => ({ id: 1, method: 'Page.navigate', sessionId, params: { url } });
    return { router, a, b, nav };
}

test('router answers a losing navigation locally with an error and does not forward it', () => {
    const { router, a, b, nav } = routerSetup();
    assert.equal(router.classifyClientRequest(a, nav('SESS-A', 'https://x.com/a')).action, 'forward');
    const decision = router.classifyClientRequest(b, nav('SESS-B', 'https://x.com/b'));
    assert.equal(decision.action, 'reply');
    assert.equal(decision.error.code, -32002);
    assert.match(decision.error.message, /TAB_LEASED/);
    assert.equal(decision.result, undefined);
});

test('router revokes the lease when Chrome refuses the acquiring navigation, keeps it on success', () => {
    const { router, a, b, nav } = routerSetup();
    const first = nav('SESS-A', 'not a url');
    const decision = router.classifyClientRequest(a, first);
    router.trackForwardedRequest(a, first, 101, decision);
    router.onChromeResponse(101, { id: 101, error: { code: -32602, message: 'Cannot navigate to invalid URL' } });
    assert.equal(router.classifyClientRequest(b, nav('SESS-B', 'https://x.com/b')).action, 'forward');

    const okReq = nav('SESS-B', 'https://x.com/b2');
    // b already holds the lease from the previous (forwarded) request; a successful response keeps it.
    const okDecision = router.classifyClientRequest(b, okReq);
    router.trackForwardedRequest(b, okReq, 102, okDecision);
    router.onChromeResponse(102, { id: 102, result: { frameId: 'F' } });
    assert.equal(router.classifyClientRequest(a, nav('SESS-A', 'https://x.com/a')).action, 'reply');
});

test('router drops a closed client\'s leases and pending lease records; reset clears everything', () => {
    const { router, a, b, nav } = routerSetup();
    const req = nav('SESS-A', 'https://x.com/a');
    router.trackForwardedRequest(a, req, 201, router.classifyClientRequest(a, req));
    assert.equal(router.pendingLease.size, 1);
    router.onClientClosed(a);
    assert.equal(router.pendingLease.size, 0);
    assert.equal(router.tabLease.leases.size, 0);
    assert.equal(router.classifyClientRequest(b, nav('SESS-B', 'https://x.com/b')).action, 'forward');
    router.reset();
    assert.equal(router.tabLease.leases.size, 0);
});
