// Unit tests for request-watch.mjs (no Chrome needed).
// Run: node --test scripts/dev/chrome-agent/tests/request-watch.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { RequestWatch } from '../request-watch.mjs';

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
    assert.match(logs[0], /slow request c7 Runtime\.evaluate sess=ABCDEF12 unanswered for 12s \(load 97 on 12 cpus, 1 pending\)/);
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
    assert.deepEqual(watch.stats(), { slowRequests: 2, loadavg1: 97.4, cpus: 12 });
});
