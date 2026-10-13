// Unit tests for stall-probe.mjs (no Chrome needed).
// Run: node --test scripts/dev/chrome-agent/tests/stall-probe.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { createStallForensics, PROBE_EXPRESSION } from '../stall-probe.mjs';

const NOW = 1_000_000;
const SESSION_PAGE = { s1: 'PAGE0001xxxx', s2: 'PAGE0001xxxx', s3: 'PAGE0002xxxx', s4: 'PAGE0003xxxx', s5: 'PAGE0004xxxx' };
const BASE = { PAGE0001xxxx: 'base1', PAGE0002xxxx: 'base2', PAGE0003xxxx: 'base3', PAGE0004xxxx: 'base4' };

function setup({ requests, probe, renderers = async () => 'renderers: 1(id1) pri 20 0.0%cpu S 0.00core', baseOverride = {} } = {}) {
    const pendingRequests = new Map(requests.map((r, i) => [i + 1, { client: { label: 'c1' }, createdAt: NOW - 12_000, ...r }]));
    const logs = [];
    const probes = [];
    const clock = { t: 0 };
    const forensics = createStallForensics({
        pendingRequests,
        pageOfSession: (s) => SESSION_PAGE[s] ?? null,
        baseSessionOfPage: (p) => (p in baseOverride ? baseOverride[p] : BASE[p]),
        describePage: (p) => `https://x.com/${p.slice(0, 8)}`,
        probe: async (session, expression, timeoutMs) => {
            probes.push({ session, expression, timeoutMs });
            clock.t += 41;
            return probe(session);
        },
        renderers,
        log: (line) => logs.push(line),
        now: () => NOW,
        clock: () => clock.t,
    });
    return { forensics, logs, probes };
}

const answer = (value) => ({ result: { result: { type: 'string', value: JSON.stringify(value) } } });

test('an answered probe reports its latency, readiness, visibility and navigation timing', async () => {
    const { forensics, logs, probes } = setup({
        requests: [{ method: 'Page.reload', sessionId: 's1' }],
        probe: () => answer(['complete', 'visible', [28, 964, 6555]]),
    });
    assert.equal(await forensics(), 'renderers: 1(id1) pri 20 0.0%cpu S 0.00core');
    assert.deepEqual(logs, ['stall page PAGE0001 [https://x.com/PAGE0001] a trivial evaluate was answered in 41ms: ready=complete visibility=visible navigation ttfb/dcl/load=28/964/6555ms']);
    assert.deepEqual(probes, [{ session: 'base1', expression: PROBE_EXPRESSION, timeoutMs: 3000 }]);
});

test('a milestone that has not happened yet reads pending; a missing navigation entry reads unavailable', async () => {
    const loading = setup({ requests: [{ method: 'Page.reload', sessionId: 's1' }], probe: () => answer(['loading', 'visible', [30, 0, 0]]) });
    await loading.forensics();
    assert.match(loading.logs[0], /navigation ttfb\/dcl\/load=30\/pending\/pendingms$/);
    const bare = setup({ requests: [{ method: 'Page.reload', sessionId: 's1' }], probe: () => answer(['complete', 'hidden', null]) });
    await bare.forensics();
    assert.match(bare.logs[0], /visibility=hidden navigation ttfb\/dcl\/load=unavailablems$/);
});

test('an unanswered probe, an error answer and a failing hook are each reported as what they are', async () => {
    const silent = setup({ requests: [{ method: 'Page.reload', sessionId: 's1' }], probe: () => { throw Object.assign(new Error('timed out'), { timedOut: true }); } });
    await silent.forensics();
    assert.deepEqual(silent.logs, ['stall page PAGE0001 [https://x.com/PAGE0001] a trivial evaluate got no answer within 3000ms']);

    const errored = setup({ requests: [{ method: 'Page.reload', sessionId: 's1' }], probe: () => ({ error: { message: 'Cannot find context' } }) });
    await errored.forensics();
    assert.match(errored.logs[0], /answered in 41ms: answered with an error \(Cannot find context\), so its process is alive$/);

    const broken = setup({ requests: [{ method: 'Page.reload', sessionId: 's1' }], probe: () => { throw new Error('Chrome not running'); } });
    await broken.forensics();
    assert.match(broken.logs[0], /could not be probed \(Chrome not running\)$/);
});

test('a page without a shared session cannot be probed and nothing is sent', async () => {
    const { forensics, logs, probes } = setup({ requests: [{ method: 'Page.reload', sessionId: 's1' }], probe: () => answer([]), baseOverride: { PAGE0001xxxx: undefined } });
    await forensics();
    assert.deepEqual(probes, []);
    assert.match(logs[0], /cannot be probed \(no shared session is attached to it\)$/);
});

test('only client requests that are slow, on a page session and not a script wait, pick a page; each page is probed once', async () => {
    const { forensics, logs, probes } = setup({
        requests: [
            { method: 'Page.reload', sessionId: 's1' },
            { method: 'Network.enable', sessionId: 's2' },
            { method: 'Page.reload', sessionId: 's3' },
            { method: 'Runtime.callFunctionOn', sessionId: 's4', awaitsScript: true },
            { method: 'Target.getTargets' },
            { method: 'Page.reload', sessionId: 'unknown' },
            { method: 'Page.reload', sessionId: 's5', createdAt: NOW - 2000 },
            { method: 'Page.reload', sessionId: 's5', client: null },
        ],
        probe: () => answer(['complete', 'visible', [1, 2, 3]]),
    });
    await forensics();
    assert.deepEqual(probes.map((p) => p.session).sort(), ['base1', 'base2']);
    assert.equal(logs.length, 2);
});

test('at most three pages are probed', async () => {
    const { forensics, probes } = setup({
        requests: ['s1', 's3', 's4', 's5'].map((sessionId) => ({ method: 'Page.reload', sessionId })),
        probe: () => answer(['complete', 'visible', [1, 2, 3]]),
    });
    await forensics();
    assert.equal(probes.length, 3);
});

test('forensics never rejects: a failing snapshot or log still yields a result', async () => {
    const failing = setup({ requests: [{ method: 'Page.reload', sessionId: 's1' }], probe: () => answer([]), renderers: async () => { throw new Error('ps failed'); } });
    assert.equal(await failing.forensics(), null);
    const sync = setup({ requests: [], probe: () => answer([]), renderers: () => { throw new Error('sync failure'); } });
    assert.equal(await sync.forensics(), null);
});
