// Unit tests for idle-pool.mjs (no Chrome needed).
// Run: node --test scripts/dev/chrome-agent/tests/idle-pool.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { IdlePool } from '../idle-pool.mjs';

const page = (targetId, url = 'about:blank') => ({ targetId, type: 'page', url });
const GRACE_MS = 600_000;

// `windows` maps targetId → window id; a tab not listed has a window of its own.
function setup({ pages, minIdle = 3, maxPages = 6, leased = new Set(), abandoned = [], windows = {} }) {
    const calls = [];
    const logs = [];
    const state = { pages };
    const cdpRequest = async (method, params) => {
        calls.push({ method, params });
        if (method === 'Target.getTargets') return { result: { targetInfos: state.pages } };
        if (method === 'Browser.getWindowForTarget') return { result: { windowId: windows[params.targetId] ?? `own-${params.targetId}` } };
        if (method === 'Target.closeTarget') {
            state.pages = state.pages.filter((t) => t.targetId !== params.targetId);
            return { result: { success: true } };
        }
        state.pages = [...state.pages, page(`NEW${state.pages.length}`)];
        return { result: { targetId: 'x' } };
    };
    const graceCalls = [];
    const clock = { ms: 0 };
    const pool = new IdlePool({
        cdpRequest, isLeased: (id) => leased.has(id), log: (l) => logs.push(l), minIdle, maxPages,
        takeAbandoned: (grace) => { graceCalls.push(grace); return abandoned; }, abandonGraceMs: GRACE_MS,
        now: () => clock.ms,
    });
    const created = () => calls.filter((c) => c.method === 'Target.createTarget');
    const closed = () => calls.filter((c) => c.method === 'Target.closeTarget').map((c) => c.params.targetId);
    return { pool, calls, logs, created, closed, graceCalls, state, clock };
}

test('a fresh Chrome with one tab is topped up to the floor, each tab in a window of its own, in the background', async () => {
    const { pool, created } = setup({ pages: [page('A')] });
    await pool.reconcile();
    assert.equal(created().length, 2);
    assert.deepEqual(created()[0].params, { url: 'about:blank', newWindow: true, background: true });
});

test('leased and loaded tabs do not count as idle', async () => {
    const { pool, created } = setup({
        pages: [page('A'), page('B'), page('C', 'https://x.com/a'), page('D')],
        leased: new Set(['B']),
    });
    await pool.reconcile();
    assert.equal(created().length, 1);
});

test('a freshly created tab whose url is still empty counts as idle (no over-creation)', async () => {
    const { pool, created } = setup({ pages: [page('A'), page('B', ''), page('C', '')] });
    await pool.reconcile();
    assert.equal(created().length, 0);
});

test('never exceeds the page cap, even when every tab is busy', async () => {
    const busy = ['A', 'B', 'C', 'D', 'E'].map((id) => page(id, `https://x.com/${id}`));
    const { pool, created } = setup({ pages: busy, maxPages: 6 });
    await pool.reconcile();
    assert.equal(created().length, 1);
    await pool.reconcile();
    assert.equal(created().length, 1);
});

test('non-page targets are ignored', async () => {
    const { pool, created } = setup({
        pages: [page('A'), page('B'), page('C'), { targetId: 'W', type: 'service_worker', url: 'https://x.com/sw.js' }],
    });
    await pool.reconcile();
    assert.equal(created().length, 0);
});

test('minIdle 0 disables the pool without touching Chrome', async () => {
    const { pool, calls } = setup({ pages: [page('A')], minIdle: 0 });
    await pool.reconcile();
    assert.equal(calls.length, 0);
});

test('overlapping reconciles are dropped, so a slow Chrome is not asked twice', async () => {
    const { pool, calls } = setup({ pages: [page('A')] });
    await Promise.all([pool.reconcile(), pool.reconcile(), pool.reconcile()]);
    assert.equal(calls.filter((c) => c.method === 'Target.getTargets').length, 1);
});

test('a failing Chrome is logged and the next tick retries', async () => {
    const logs = [];
    let fail = true;
    const pool = new IdlePool({
        cdpRequest: async (method) => {
            if (fail) throw new Error('Chrome not running');
            return method === 'Target.getTargets' ? { result: { targetInfos: [page('A'), page('B'), page('C')] } } : { result: {} };
        },
        isLeased: () => false, log: (l) => logs.push(l), minIdle: 3, maxPages: 6,
        takeAbandoned: () => [], abandonGraceMs: 1,
    });
    await pool.reconcile();
    assert.match(logs[0], /reconcile skipped.*Chrome not running/);
    fail = false;
    await pool.reconcile();
    assert.equal(pool.running, false);
});

test('a createTarget error stops the batch instead of looping', async () => {
    const calls = [];
    const pool = new IdlePool({
        cdpRequest: async (method) => {
            calls.push(method);
            return method === 'Target.getTargets'
                ? { result: { targetInfos: [page('A')] } }
                : { error: { message: 'no browser window' } };
        },
        isLeased: () => false, log() {}, minIdle: 3, maxPages: 6, takeAbandoned: () => [], abandonGraceMs: 1,
    });
    await pool.reconcile();
    assert.equal(calls.filter((m) => m === 'Target.createTarget').length, 1);
});

test('an abandoned tab is closed and replaced, other busy tabs are left alone', async () => {
    const { pool, closed, created, graceCalls } = setup({
        pages: [page('A'), page('B'), page('LEAK', 'https://x.com/a'), page('MINE', 'https://x.com/b')],
        abandoned: ['LEAK'],
    });
    await pool.reconcile();
    assert.deepEqual(closed(), ['LEAK']);
    assert.deepEqual(graceCalls, [GRACE_MS]);
    assert.equal(created().length, 1);
});

test('an expired tab that was released, re-leased or is already gone is not closed', async () => {
    const { pool, closed } = setup({
        pages: [page('A'), page('B'), page('C'), page('RELEASED'), page('RELEASED2', 'https://x.com/c')],
        leased: new Set(['RELEASED2']),
        abandoned: ['RELEASED', 'RELEASED2', 'GONE'],
    });
    await pool.reconcile();
    assert.deepEqual(closed(), []);
});

test('abandoned tabs are not reclaimed when the pool is disabled', async () => {
    const { pool, closed } = setup({ pages: [page('A', 'https://x.com/a')], minIdle: 0, abandoned: ['A'] });
    await pool.reconcile();
    assert.deepEqual(closed(), []);
});

test('blank tabs sharing one window are hidden tabs and do not count as idle', async () => {
    const { pool, created } = setup({
        pages: [page('A'), page('B'), page('C')],
        windows: { A: 1, B: 1, C: 1 },
    });
    await pool.reconcile();
    assert.equal(created().length, 3);
});

test('a blank tab in a shared window is left alone until it has been unused for the whole grace period', async () => {
    const { pool, closed, created, state, clock } = setup({ pages: [page('A'), page('B'), page('C')], windows: { A: 1, B: 1, C: 1 } });
    await pool.reconcile();
    assert.equal(created().length, 3);
    // A client may have created and attached such a tab a moment ago (BUG-DG-2026-10-12-010).
    for (const ms of [0, 5, 250, 2000, GRACE_MS - 1]) {
        clock.ms = ms;
        await pool.reconcile();
        assert.deepEqual(closed(), [], `kept at +${ms} ms`);
    }
    clock.ms = GRACE_MS;
    await pool.reconcile();
    assert.deepEqual(closed().sort(), ['A', 'B', 'C']);
    assert.equal(state.pages.length, 3);
    await pool.reconcile();
    assert.equal(created().length, 3);
});

test('a shared-window tab that was used in between does not keep its old blank time', async () => {
    const { pool, closed, state, clock } = setup({ pages: [page('A'), page('B')], windows: { A: 1, B: 1 }, minIdle: 1, maxPages: 12 });
    const setUrl = (id, url) => { state.pages = state.pages.map((t) => (t.targetId === id ? { ...t, url } : t)); };
    await pool.reconcile();
    clock.ms = GRACE_MS - 1000;
    setUrl('A', 'https://x.com/a');
    await pool.reconcile();
    setUrl('A', 'about:blank');
    clock.ms = GRACE_MS - 500;
    await pool.reconcile();
    clock.ms = GRACE_MS + 100;
    await pool.reconcile();
    assert.deepEqual(closed(), ['B'], 'B was blank throughout; A started over when it went blank again');
    // With B gone A is alone in its window: a usable idle tab, no longer a shared one.
    clock.ms = GRACE_MS * 2;
    await pool.reconcile();
    assert.deepEqual(closed(), ['B']);
});

test('a loaded tab in a shared window is never closed, a leased blank one neither', async () => {
    const { pool, closed, clock } = setup({
        pages: [page('A', 'https://x.com/a'), page('B'), page('L'), page('S1'), page('S2'), page('S3')],
        windows: { A: 1, B: 1, L: 1 },
        leased: new Set(['L']),
        maxPages: 12,
    });
    await pool.reconcile();
    clock.ms = GRACE_MS * 10;
    await pool.reconcile();
    assert.deepEqual(closed(), ['B']);
});

test('shared-window blanks that fill the cap block the pool until their grace is over, then make room', async () => {
    const { pool, closed, created, clock } = setup({
        pages: ['A', 'B', 'C', 'D'].map((id) => page(id)),
        windows: { A: 1, B: 1, C: 1, D: 1 },
        minIdle: 3,
        maxPages: 4,
    });
    await pool.reconcile();
    assert.deepEqual(closed(), []);
    assert.equal(created().length, 0);
    clock.ms = GRACE_MS;
    await pool.reconcile();
    assert.deepEqual(closed(), ['A', 'B', 'C', 'D']);
    assert.equal(created().length, 3);
});

test('a tab whose window cannot be resolved is treated as alone in its window', async () => {
    const calls = [];
    const pool = new IdlePool({
        cdpRequest: async (method, params) => {
            calls.push(method);
            if (method === 'Target.getTargets') return { result: { targetInfos: [page('A'), page('B'), page('C')] } };
            return { error: { message: 'not supported' } };
        },
        isLeased: () => false, log() {}, minIdle: 3, maxPages: 6, takeAbandoned: () => [], abandonGraceMs: 1,
    });
    await pool.reconcile();
    assert.equal(calls.filter((m) => m === 'Target.createTarget').length, 0);
    assert.equal(calls.filter((m) => m === 'Target.closeTarget').length, 0);
});

test('a tab keeps its window id, so Chrome is asked once per tab', async () => {
    const { pool, calls } = setup({ pages: [page('A'), page('B'), page('C')] });
    await pool.reconcile();
    await pool.reconcile();
    assert.equal(calls.filter((c) => c.method === 'Browser.getWindowForTarget').length, 3);
});

test('sharedWindowPages counts the hidden tabs: pages beyond the first in their window', async () => {
    const { pool } = setup({
        pages: [page('A'), page('B'), page('C'), page('D', 'https://x.com/d')],
        windows: { A: 1, B: 1, C: 1, D: 2 },
    });
    assert.equal(pool.sharedWindowPages, null);
    await pool.reconcile();
    assert.equal(pool.sharedWindowPages, 2);
});

test('sharedWindowPages is 0 when every tab has a window of its own', async () => {
    const { pool } = setup({ pages: [page('A'), page('B'), page('C')] });
    await pool.reconcile();
    assert.equal(pool.sharedWindowPages, 0);
});
