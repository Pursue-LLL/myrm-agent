// Unit tests for process-snapshot.mjs (no Chrome needed).
// Run: node --test scripts/dev/chrome-agent/tests/process-snapshot.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { summarizeRenderers, snapshotRenderers } from '../process-snapshot.mjs';

const PS = [
    '  500     1  31   0.0 Ss   /Applications/Google Chrome.app/Contents/MacOS/Google Chrome --user-data-dir=/p',
    '31218   500   4   0.0 S    /x/Chrome Helper (Renderer) --type=renderer --renderer-client-id=10 --lang=zh-CN',
    '31096   500  20   3.2 S    /x/Chrome Helper (Renderer) --type=renderer --renderer-client-id=6 --lang=zh-CN',
    '31300   500  20   0.1 S    /x/Chrome Helper (GPU) --type=gpu-process',
    '41000   999  20   9.9 S    /y/Other Helper (Renderer) --type=renderer --renderer-client-id=3',
].join('\n');

test('only renderer children of Chrome are listed, in pid order, with priority, cpu share and state', () => {
    assert.equal(
        summarizeRenderers(PS, 500),
        'renderers: 31096(id6) pri 20 3.2%cpu S, 31218(id10) pri 4 0.0%cpu S',
    );
});

test('no renderer children (Chrome gone or not yet spawned) gives null', () => {
    assert.equal(summarizeRenderers(PS, 12345), null);
    assert.equal(summarizeRenderers('', 500), null);
});

test('snapshotRenderers runs ps once and summarizes it', async () => {
    const calls = [];
    const exec = (cmd, args, opts, cb) => { calls.push([cmd, args.join(' ')]); cb(null, PS); };
    assert.match(await snapshotRenderers(500, exec), /^renderers: 31096\(id6\)/);
    assert.deepEqual(calls, [['ps', '-Ao pid=,ppid=,pri=,pcpu=,stat=,command=']]);
});

test('snapshotRenderers never rejects: a ps failure or a missing pid is null', async () => {
    assert.equal(await snapshotRenderers(500, (cmd, args, opts, cb) => cb(new Error('boom'))), null);
    assert.equal(await snapshotRenderers(null, () => assert.fail('must not spawn ps')), null);
});
