// Unit tests for process-snapshot.mjs (no Chrome needed).
// Run: node --test scripts/dev/chrome-agent/tests/process-snapshot.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseCpuTime, summarizeRenderers, snapshotRenderers } from '../process-snapshot.mjs';

const ps = (rows) => rows.map(([pid, ppid, pri, pcpu, stat, time, cmd]) => `${pid} ${ppid} ${pri} ${pcpu} ${stat} ${time} ${cmd}`).join('\n');
const RENDERER = (id) => `/x/Chrome Helper (Renderer) --type=renderer --renderer-client-id=${id} --lang=zh-CN`;

const FIRST = ps([
    [500, 1, 31, '0.0', 'Ss', '1:00.00', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --user-data-dir=/p'],
    [31218, 500, 4, '0.0', 'S', '0:10.00', RENDERER(10)],
    [31096, 500, 20, '3.2', 'R', '2:00.00', RENDERER(6)],
    [31300, 500, 20, '0.1', 'S', '0:05.00', '/x/Chrome Helper (GPU) --type=gpu-process'],
    [41000, 999, 20, '9.9', 'S', '0:01.00', '/y/Other Helper (Renderer) --type=renderer --renderer-client-id=3'],
]);

test('only renderer children of Chrome are listed, in pid order, with priority, cpu share and state', () => {
    assert.equal(
        summarizeRenderers(FIRST, 500),
        'renderers: 31096(id6) pri 20 3.2%cpu R, 31218(id10) pri 4 0.0%cpu S',
    );
});

test('no renderer children (Chrome gone or not yet spawned) gives null', () => {
    assert.equal(summarizeRenderers(FIRST, 12345), null);
    assert.equal(summarizeRenderers('', 500), null);
});

test('ps TIME parses minutes, hours and days; garbage is NaN', () => {
    assert.equal(parseCpuTime('0:01.81'), 1.81);
    assert.equal(parseCpuTime('12:34.56'), 754.56);
    assert.equal(parseCpuTime('2:03:04'), 7384);
    assert.equal(parseCpuTime('1-02:03:04'), 86400 + 7384);
    assert.ok(Number.isNaN(parseCpuTime('abc')));
});

test('core share is the cpu time used over the window divided by its wall time', () => {
    // 31096 burned 1.96 s of CPU in 2 s (a busy page); 31218 used 0.1 s (starved or idle).
    const second = ps([
        [31218, 500, 4, '0.0', 'S', '0:10.10', RENDERER(10)],
        [31096, 500, 20, '98.0', 'R', '2:01.96', RENDERER(6)],
    ]);
    assert.equal(
        summarizeRenderers(FIRST, 500, second, 2),
        'renderers: 31096(id6) pri 20 3.2%cpu R 0.98core, 31218(id10) pri 4 0.0%cpu S 0.05core',
    );
});

test('a renderer that is missing from the second sample, or an unparsable time, gets no core share', () => {
    const second = ps([[31096, 500, 20, '98.0', 'R', 'garbage', RENDERER(6)]]);
    assert.equal(
        summarizeRenderers(FIRST, 500, second, 2),
        'renderers: 31096(id6) pri 20 3.2%cpu R, 31218(id10) pri 4 0.0%cpu S',
    );
    assert.equal(summarizeRenderers(FIRST, 500, FIRST, 0), 'renderers: 31096(id6) pri 20 3.2%cpu R, 31218(id10) pri 4 0.0%cpu S');
});

test('snapshotRenderers samples ps twice a window apart and reports the core share', async () => {
    const calls = [];
    const outputs = [FIRST, ps([[31096, 500, 20, '98.0', 'R', '2:01.96', RENDERER(6)]])];
    const exec = (cmd, args, opts, cb) => { calls.push([cmd, args.join(' ')]); cb(null, outputs[calls.length - 1]); };
    const sleeps = [];
    const summary = await snapshotRenderers(500, exec, { windowMs: 5, sleep: async (ms) => { sleeps.push(ms); await new Promise((r) => setTimeout(r, ms)); } });
    assert.match(summary, /^renderers: 31096\(id6\) pri 20 3\.2%cpu R \d+\.\d\dcore, 31218\(id10\) pri 4 0\.0%cpu S$/);
    assert.deepEqual(calls, Array(2).fill(['ps', '-Ao pid=,ppid=,pri=,pcpu=,stat=,time=,command=']));
    assert.deepEqual(sleeps, [5]);
});

test('a failing second ps only drops the core shares', async () => {
    let n = 0;
    const exec = (cmd, args, opts, cb) => (++n === 1 ? cb(null, FIRST) : cb(new Error('boom')));
    assert.equal(
        await snapshotRenderers(500, exec, { windowMs: 0, sleep: async () => {} }),
        'renderers: 31096(id6) pri 20 3.2%cpu R, 31218(id10) pri 4 0.0%cpu S',
    );
});

test('snapshotRenderers never rejects: a ps failure or a missing pid is null', async () => {
    assert.equal(await snapshotRenderers(500, (cmd, args, opts, cb) => cb(new Error('boom')), { windowMs: 0, sleep: async () => {} }), null);
    assert.equal(await snapshotRenderers(null, () => assert.fail('must not spawn ps')), null);
});
