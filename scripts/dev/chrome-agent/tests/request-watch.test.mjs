// Unit tests for request-watch.mjs (no Chrome needed).
// Run: node --test scripts/dev/chrome-agent/tests/request-watch.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { RequestWatch, describeScript } from '../request-watch.mjs';

function setup() {
    const pendingRequests = new Map();
    const logs = [];
    const clock = { t: 1_000_000 };
    const watch = new RequestWatch({
        pendingRequests, log: (l) => logs.push(l), slowMs: 10_000, now: () => clock.t, loadavg: () => [97.4, 80, 60], cpus: 12,
    });
    const add = (id, extra = {}) => pendingRequests.set(id, {
        client: { label: 'c7' }, method: 'Runtime.evaluate', sessionId: 'ABCDEF1234567890', createdAt: clock.t, ...extra,
    });
    return { watch, pendingRequests, logs, clock, add };
}

test('a request answered within the threshold is never logged', () => {
    const { watch, logs, clock, add, pendingRequests } = setup();
    add(1);
    clock.t += 9_000;
    watch.sweep();
    pendingRequests.delete(1);
    watch.sweep();
    assert.deepEqual(logs, []);
    assert.equal(watch.stats().slowRequests, 0);
});

test('a request unanswered past the threshold is logged once with method, connection, session and load', () => {
    const { watch, logs, clock, add } = setup();
    add(1);
    clock.t += 12_000;
    watch.sweep();
    watch.sweep();
    assert.equal(logs.length, 1);
    assert.match(logs[0], /slow request c7 Runtime\.evaluate sess=ABCDEF12 \[session unknown to the proxy\] unanswered for 12s \(load 97 on 12 cpus, 1 pending\)/);
    assert.equal(watch.stats().slowRequests, 1);
});

test('the log says how long Chrome has been up, so a stall can be told from an aged browser', () => {
    const pendingRequests = new Map([[1, { client: { label: 'c2' }, method: 'Runtime.enable', createdAt: 0 }]]);
    const logs = [];
    const watch = new RequestWatch({
        pendingRequests, log: (l) => logs.push(l), slowMs: 10_000, now: () => 12_000, loadavg: () => [36, 30, 20], cpus: 12,
        chromeAgeMs: () => 7.7 * 60_000,
    });
    watch.sweep();
    assert.match(logs[0], /\(load 36 on 12 cpus, 1 pending, chrome up 8m\)/);
});

test('the log names what the stalled session is attached to', () => {
    const pendingRequests = new Map([[1, { client: { label: 'c2' }, method: 'Runtime.enable', sessionId: 'ABCDEF1234', createdAt: 0 }]]);
    const logs = [];
    new RequestWatch({
        pendingRequests, log: (l) => logs.push(l), slowMs: 10_000, now: () => 12_000, loadavg: () => [36, 30, 20], cpus: 12,
        describeSession: (id) => (id === 'ABCDEF1234' ? 'base iframe https://platform.x.com/embed' : null),
    }).sweep();
    assert.match(logs[0], /sess=ABCDEF12 \[base iframe https:\/\/platform\.x\.com\/embed\] unanswered for 12s/);
});

test('slow requests on a session the proxy no longer knows are counted apart from those on live sessions', () => {
    const pendingRequests = new Map([
        [1, { client: { label: 'c2' }, method: 'Runtime.enable', sessionId: 'GONE000011', createdAt: 0 }],
        [2, { client: { label: 'c2' }, method: 'Runtime.evaluate', sessionId: 'LIVE000022', createdAt: 0 }],
    ]);
    const watch = new RequestWatch({
        pendingRequests, log() {}, slowMs: 10_000, now: () => 12_000, loadavg: () => [1, 1, 1], cpus: 12,
        describeSession: (id) => (id === 'LIVE000022' ? 'owned page https://x.com/a' : null),
    });
    watch.sweep();
    assert.deepEqual([watch.stats().slowRequests, watch.stats().slowRequestsOnUnknownSession], [2, 1]);
});

test('when the request leaves the pending set the log says how long it was seen pending', () => {
    const { watch, logs, clock, add, pendingRequests } = setup();
    add(1);
    clock.t += 12_000;
    watch.sweep();
    clock.t += 2_000;
    watch.sweep();
    clock.t += 2_000;
    pendingRequests.delete(1);
    watch.sweep();
    assert.equal(logs.length, 2);
    assert.match(logs[1], /left the pending set after at least 14s/);
    watch.sweep();
    assert.equal(logs.length, 2);
});

test('proxy-internal requests (no client) are ignored', () => {
    const { watch, logs, clock, add } = setup();
    add(1, { client: null });
    clock.t += 30_000;
    watch.sweep();
    assert.deepEqual(logs, []);
});

test('a reused proxy id is a different request', () => {
    const { watch, logs, clock, add, pendingRequests } = setup();
    add(1);
    clock.t += 12_000;
    watch.sweep();
    pendingRequests.delete(1);
    clock.t += 1_000;
    add(1);
    watch.sweep();
    assert.match(logs[1], /left the pending set/);
    assert.equal(watch.flagged.size, 0);
});

test('stats report the slow count, load and cpu count for /proxy/status', () => {
    const { watch, clock, add } = setup();
    add(1);
    add(2, { method: 'Page.reload' });
    clock.t += 15_000;
    watch.sweep();
    assert.deepEqual(watch.stats(), { slowRequests: 2, slowRequestsOnUnknownSession: 2, scriptWaits: 0, loadavg1: 97.4, cpus: 12 });
});

test('the first stall of a burst logs one renderer snapshot; the next burst waits out the cooldown', async () => {
    const { pendingRequests, logs, clock, add } = setup();
    let snapshots = 0;
    const watch = new RequestWatch({
        pendingRequests, log: (l) => logs.push(l), slowMs: 10_000, now: () => clock.t, loadavg: () => [97.4, 80, 60], cpus: 12,
        stallSnapshot: async () => `renderers: ${++snapshots}`,
    });
    add(1); add(2);
    clock.t += 12_000;
    watch.sweep();
    await Promise.resolve();
    assert.equal(snapshots, 1);
    assert.equal(logs.filter((l) => l.startsWith('stall snapshot')).length, 1);
    assert.equal(logs.find((l) => l.startsWith('stall snapshot')), 'stall snapshot renderers: 1');

    add(3);
    clock.t += 12_000;
    watch.sweep();
    await Promise.resolve();
    assert.equal(snapshots, 1, 'inside the 30 s cooldown');

    add(4);
    clock.t += 30_000;
    watch.sweep();
    await Promise.resolve();
    assert.equal(snapshots, 2);
});

test('a failing or empty snapshot adds no line and does not break the sweep', async () => {
    const { pendingRequests, logs, clock, add } = setup();
    const watch = new RequestWatch({
        pendingRequests, log: (l) => logs.push(l), slowMs: 10_000, now: () => clock.t, loadavg: () => [1, 1, 1], cpus: 12,
        stallSnapshot: () => Promise.reject(new Error('ps failed')),
    });
    add(1);
    clock.t += 12_000;
    watch.sweep();
    await Promise.resolve();
    assert.equal(logs.length, 1);
    assert.match(logs[0], /^slow request/);
});

test('a request waiting on a page script (awaitPromise) is logged as a script wait, not as a slow request', () => {
    const { watch, pendingRequests, logs, clock, add } = setup();
    let snapshots = 0;
    watch.stallSnapshot = async () => { snapshots++; return 'x'; };
    add(1, { method: 'Runtime.callFunctionOn', awaitsScript: true });
    clock.t += 12_000;
    watch.sweep();
    pendingRequests.delete(1);
    watch.sweep();
    assert.deepEqual(logs, [
        'script wait c7 Runtime.callFunctionOn (awaitPromise) still running after 12s',
        'script wait c7 Runtime.callFunctionOn left the pending set after at least 12s (answered, or timed out by the 60 s reaper)',
    ]);
    assert.equal(snapshots, 0);
    assert.equal(watch.stats().slowRequests, 0);
    assert.equal(watch.stats().scriptWaits, 1);
});

test('a slow request names the head of the script it runs', () => {
    const { watch, logs, clock, add } = setup();
    add(1, { script: 'document.querySelectorAll(...)' });
    clock.t += 10_000;
    watch.sweep();
    assert.match(logs[0], /slow request c7 Runtime\.evaluate sess=ABCDEF12 \[session unknown to the proxy\] script "document\.querySelectorAll\(\.\.\.\)" unanswered for 10s/);
});

test('a request without a script (non-Runtime method) logs no script clause', () => {
    const { watch, logs, clock, add } = setup();
    add(1, { method: 'Page.navigate' });
    clock.t += 10_000;
    watch.sweep();
    assert.doesNotMatch(logs[0], /script "/);
});

test('describeScript keeps a whitespace-collapsed 60-char head of an expression or function declaration', () => {
    assert.equal(describeScript({ expression: '  a\n\n  b  ' }), 'a b');
    assert.equal(describeScript({ functionDeclaration: 'function () {\n return 1 }' }), 'function () { return 1 }');
    assert.equal(describeScript({ expression: 'x'.repeat(61) }), `${'x'.repeat(60)}...`);
    assert.equal(describeScript({ url: 'https://x.com' }), null);
    assert.equal(describeScript(undefined), null);
});
