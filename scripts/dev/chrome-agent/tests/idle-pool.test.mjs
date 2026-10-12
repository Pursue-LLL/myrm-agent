// Unit tests for idle-pool.mjs (no Chrome needed).
// Run: node --test scripts/dev/chrome-agent/tests/idle-pool.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { IdlePool } from '../idle-pool.mjs';

const page = (targetId, url = 'about:blank') => ({ targetId, type: 'page', url });

function setup({ pages, minIdle = 3, maxPages = 6, leased = new Set() }) {
    const calls = [];
    const logs = [];
    const state = { pages };
    const cdpRequest = async (method, params) => {
        calls.push({ method, params });
        if (method === 'Target.getTargets') return { result: { targetInfos: state.pages } };
        state.pages = [...state.pages, page(`NEW${state.pages.length}`)];
        return { result: { targetId: 'x' } };
    };
    const pool = new IdlePool({ cdpRequest, isLeased: (id) => leased.has(id), log: (l) => logs.push(l), minIdle, maxPages });
    const created = () => calls.filter((c) => c.method === 'Target.createTarget');
    return { pool, calls, logs, created, state };
}

test('a fresh Chrome with one tab is topped up to the floor, in the background', async () => {
    const { pool, created } = setup({ pages: [page('A')] });
    await pool.reconcile();
    assert.equal(created().length, 2);
    assert.deepEqual(created()[0].params, { url: 'about:blank', background: true });
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
        isLeased: () => false, log() {}, minIdle: 3, maxPages: 6,
    });
    await pool.reconcile();
    assert.equal(calls.filter((m) => m === 'Target.createTarget').length, 1);
});
