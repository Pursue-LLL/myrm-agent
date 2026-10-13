// Unit tests for hang-guard.mjs (no Chrome needed).
// Run: node --test scripts/dev/chrome-agent/tests/hang-guard.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { HangGuard } from '../hang-guard.mjs';

const MIN = 60_000;

function setup(overrides = {}) {
    const pendingRequests = new Map();
    const logs = [];
    const replies = [];
    const abandoned = [];
    const probes = [];
    const closes = [];
    const clock = { t: 10_000_000 };
    const world = {
        verdict: 'silent',
        closeError: null,
        /** sessionId → page target */
        pageOf: { s1: 'PAGE0001', s2: 'PAGE0001', s3: 'PAGE0002', s4: 'PAGE0003', s5: 'PAGE0004', s6: 'PAGE0005' },
        /** page target → shared session to probe with */
        base: { PAGE0001: 'base1', PAGE0002: 'base2', PAGE0003: 'base3', PAGE0004: 'base4', PAGE0005: 'base5' },
    };
    const guard = new HangGuard({
        pendingRequests,
        now: () => clock.t,
        log: (line) => logs.push(line),
        loadavg: () => [97.4, 80, 60],
        cpus: 12,
        chromeAgeMs: () => 5 * MIN,
        reply: (req, message) => replies.push({ id: req.originalId, message }),
        abandon: (proxyId) => abandoned.push(proxyId),
        pageOfSession: (sessionId) => world.pageOf[sessionId] ?? null,
        baseSessionOfPage: (page) => world.base[page],
        describePage: (page) => `https://x.com/${page}`,
        probe: async (session, ms) => {
            probes.push({ session, ms });
            return typeof world.verdict === 'function' ? world.verdict(session) : world.verdict;
        },
        closePage: async (page) => {
            closes.push(page);
            if (world.closeError) throw new Error(world.closeError);
        },
        ...overrides,
    });
    const add = (proxyId, extra = {}) => pendingRequests.set(proxyId, {
        clientWs: {}, client: { label: 'c4' }, originalId: proxyId * 10, method: 'Runtime.evaluate', sessionId: 's1', createdAt: clock.t, ...extra,
    });
    return { guard, pendingRequests, logs, replies, abandoned, probes, closes, clock, world, add };
}

test('a request is replied the timeout only once it is older than 60 s', async () => {
    const { guard, pendingRequests, replies, abandoned, clock, add, probes } = setup();
    add(1);
    clock.t += MIN;
    await guard.sweep();
    assert.equal(pendingRequests.size, 1, 'exactly 60 s old is not yet stale');
    assert.deepEqual(replies, []);
    clock.t += 1;
    await guard.sweep();
    assert.equal(pendingRequests.size, 0);
    assert.deepEqual(replies, [{ id: 10, message: 'CDP request timeout (60s)' }]);
    assert.deepEqual(abandoned, [1]);
    assert.equal(probes.length, 2, 'the probe and its confirmation');
});

test('a hung page (the probe stays silent) is closed, its other pending requests fail at once, healthy pages are untouched', async () => {
    const { guard, pendingRequests, replies, abandoned, probes, closes, logs, clock, add } = setup();
    add(1);
    clock.t += MIN + 1;
    add(2, { sessionId: 's2', method: 'Page.reload' });
    add(3, { sessionId: 's3' });
    await guard.sweep();
    assert.deepEqual(probes, [{ session: 'base1', ms: 30_000 }, { session: 'base1', ms: 3_000 }]);
    assert.deepEqual(closes, ['PAGE0001']);
    assert.equal(replies[0].message, 'CDP request timeout (60s)');
    assert.match(replies[1].message, /^PAGE_HUNG: this page stopped answering \(a trivial probe got no reply for 30s\)/);
    assert.match(replies[1].message, /report PAGE_STALL$/);
    assert.deepEqual(replies.map((r) => r.id), [10, 20]);
    assert.deepEqual(abandoned, [1, 2]);
    assert.deepEqual([...pendingRequests.keys()], [3], 'the request on the other page keeps waiting');
    assert.equal(logs.length, 1);
    assert.match(logs[0], /^hang guard: closed hung page PAGE0001 \(https:\/\/x\.com\/PAGE0001\): Runtime\.evaluate from c4 unanswered for 60s and neither the probe \(30s\) nor a second one \(3s\) got a reply \(load 97 on 12 cpus, chrome up 5m\); 1 other pending request\(s\) failed$/);
    assert.deepEqual(guard.stats(), { hungPagesClosed: 1, hangProbesAnswered: 0 });
});

test('a page that answers the probe is slow, not hung: nothing is closed and it is not probed again for a minute', async () => {
    const { guard, replies, probes, closes, logs, clock, add, world } = setup();
    world.verdict = 'alive';
    add(1);
    clock.t += MIN + 1;
    await guard.sweep();
    assert.deepEqual(closes, []);
    assert.deepEqual(replies.map((r) => r.message), ['CDP request timeout (60s)']);
    assert.match(logs[0], /^hang guard: page PAGE0001 \(https:\/\/x\.com\/PAGE0001\) is slow, not hung \(Runtime\.evaluate from c4 was reaped, a probe was answered\)$/);
    assert.deepEqual(guard.stats(), { hungPagesClosed: 0, hangProbesAnswered: 1 });

    add(2, { createdAt: clock.t - MIN - 1 });
    clock.t += 10_000;
    await guard.sweep();
    assert.equal(probes.length, 1, 'still inside the recheck period');
    clock.t += MIN;
    add(3, { createdAt: clock.t - MIN - 1 });
    await guard.sweep();
    assert.equal(probes.length, 2, 'probed again after the recheck period');
});

test('a page that recovers or is replaced between the probe and the close (the confirmation is answered) is not closed', async () => {
    const { guard, replies, closes, logs, add, clock, world } = setup();
    const verdicts = ['silent', 'alive'];
    world.verdict = () => verdicts.shift();
    add(1);
    clock.t += MIN + 1;
    add(2, { sessionId: 's2' });
    await guard.sweep();
    assert.deepEqual(closes, []);
    assert.deepEqual(replies.map((r) => r.message), ['CDP request timeout (60s)']);
    assert.match(logs[0], /is slow, not hung/);
    assert.deepEqual(guard.stats(), { hungPagesClosed: 0, hangProbesAnswered: 1 });
});

test('a probe that could not run (Chrome busy restarting, session gone) closes nothing and is not counted as an answer', async () => {
    const { guard, closes, add, clock, world } = setup();
    world.verdict = 'unavailable';
    add(1);
    clock.t += MIN + 1;
    await guard.sweep();
    assert.deepEqual(closes, []);
    assert.equal(guard.stats().hangProbesAnswered, 0);
});

test('a probe hook that throws is contained: the sweep resolves, nothing is closed, the page is checked again later', async () => {
    const { guard, closes, logs, add, clock } = setup({ probe: () => { throw new Error('boom'); } });
    add(1);
    clock.t += MIN + 1;
    await guard.sweep();
    assert.deepEqual(closes, []);
    assert.equal(guard.checks.get('PAGE0001') > clock.t, true);
    assert.deepEqual(logs, []);
});

test('a lookup that fails while the page is being closed is logged and does not lock the page out of future checks', async () => {
    let lookups = 0;
    const { guard, closes, logs, add, clock } = setup({
        pageOfSession: () => {
            if (++lookups > 1) throw new Error('lookup failed');
            return 'PAGE0001';
        },
    });
    add(1);
    clock.t += MIN + 1;
    add(2);
    await guard.sweep();
    assert.deepEqual(closes, []);
    assert.match(logs[0], /^hang guard: check of page PAGE0001 failed \(lookup failed\)$/);
    assert.equal(Number.isFinite(guard.checks.get('PAGE0001')), true);
});

test('a page without a shared session cannot be probed and is left alone', async () => {
    const { guard, closes, probes, logs, add, clock, world } = setup();
    delete world.base.PAGE0001;
    add(1);
    clock.t += MIN + 1;
    await guard.sweep();
    assert.deepEqual([probes, closes], [[], []]);
    assert.match(logs[0], /page PAGE0001 .* cannot be probed/);
});

test('requests that say nothing about a page are reaped but never probed: unknown session, browser-level, proxy-internal', async () => {
    const { guard, replies, probes, closes, add, clock } = setup();
    add(1, { sessionId: 'unknown-session' });
    add(2, { sessionId: undefined, method: 'Target.getTargets' });
    add(3, { client: null });
    clock.t += MIN + 1;
    await guard.sweep();
    assert.equal(replies.length, 3);
    assert.deepEqual([probes, closes], [[], []]);
});

test('several stale requests on one page cause a single probe', async () => {
    const { guard, probes, closes, add, clock } = setup();
    add(1); add(2, { sessionId: 's2' }); add(3, { method: 'Page.reload' });
    clock.t += MIN + 1;
    await guard.sweep();
    assert.deepEqual(probes.map((p) => p.ms), [30_000, 3_000], 'one probe and its confirmation, not one per request');
    assert.deepEqual(closes, ['PAGE0001']);
});

test('a probe still in flight is not duplicated by the next sweep', async () => {
    let release;
    const gate = new Promise((resolve) => { release = () => resolve('silent'); });
    const { guard, probes, closes, add, clock, world } = setup();
    world.verdict = () => gate;
    add(1);
    clock.t += MIN + 1;
    const first = guard.sweep();
    add(2, { createdAt: clock.t - MIN - 1 });
    await guard.sweep();
    assert.equal(probes.length, 1, 'the page is already being probed');
    release();
    await first;
    assert.deepEqual(closes, ['PAGE0001']);
});

test('more than three closures in ten minutes points at Chrome or the host: the guard only logs until the window passes', async () => {
    const { guard, closes, logs, add, clock } = setup();
    for (const [i, sessionId] of ['s1', 's3', 's4'].entries()) {
        add(i + 1, { sessionId });
        clock.t += MIN + 1;
        await guard.sweep();
    }
    assert.deepEqual(closes, ['PAGE0001', 'PAGE0002', 'PAGE0003']);
    add(10, { sessionId: 's5' });
    clock.t += MIN + 1;
    await guard.sweep();
    assert.deepEqual(closes, ['PAGE0001', 'PAGE0002', 'PAGE0003'], 'the fourth hung page is not closed');
    assert.match(logs.at(-1), /^hang guard: page PAGE0004 .* is hung but NOT closed: 3 pages were closed in the last 10 min/);

    clock.t += 10 * MIN;
    add(11, { sessionId: 's6' });
    clock.t += MIN + 1;
    await guard.sweep();
    assert.equal(closes.at(-1), 'PAGE0005', 'closing resumes once the window has passed');
});

test('a close Chrome refuses leaves the page open, its pending requests waiting and the guard counting nothing', async () => {
    const { guard, pendingRequests, replies, logs, add, clock, world } = setup();
    world.closeError = 'No target with given id';
    add(1);
    clock.t += MIN + 1;
    add(2, { sessionId: 's2' });
    await guard.sweep();
    assert.equal(guard.stats().hungPagesClosed, 0);
    assert.deepEqual([...pendingRequests.keys()], [2]);
    assert.deepEqual(replies.map((r) => r.message), ['CDP request timeout (60s)']);
    assert.match(logs[0], /is hung but could not be closed \(No target with given id\)/);
});

test('the requests to fail are collected before the close, when the sessions still resolve to the page', async () => {
    const { guard, replies, add, clock, world } = setup({
        closePage: async () => { Object.keys(world.pageOf).forEach((k) => delete world.pageOf[k]); },
    });
    add(1);
    clock.t += MIN + 1;
    add(2, { sessionId: 's2' });
    await guard.sweep();
    assert.equal(replies.length, 2);
    assert.match(replies[1].message, /^PAGE_HUNG/);
});
