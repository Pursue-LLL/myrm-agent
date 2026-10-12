// A live-test runner that is SIGKILLed cannot clean up after itself. The detached watchdog
// (live/reaper.mjs) must then stop the sandbox's proxy and delete the temp profile, must leave
// a sandbox the runner already cleaned alone, and must never signal a reused pid.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { after, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { recordProxyPid, removeSandbox, STOPPED_MARKER } from './live/sandbox-cleanup.mjs';

const REAPER = path.resolve(path.dirname(fileURLToPath(import.meta.url)), 'live/reaper.mjs');
const IDLE = ['-e', 'setInterval(() => {}, 1000)'];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const alive = (pid) => {
    try { process.kill(pid, 0); return true; } catch { return false; }
};
const waitFor = async (predicate, ms = 15000) => {
    for (let waited = 0; waited < ms; waited += 100) {
        if (predicate()) return true;
        await sleep(100);
    }
    return predicate();
};

const spawned = [];
const profiles = [];
after(() => {
    for (const child of spawned) { try { child.kill('SIGKILL'); } catch { /* gone */ } }
    for (const dir of profiles) fs.rmSync(dir, { recursive: true, force: true });
});

/** A temp profile plus a stand-in proxy whose command line carries the profile path, as the real one does. */
function sandbox() {
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'chrome-agent-live-'));
    profiles.push(profile);
    fs.mkdirSync(path.join(profile, 'chrome'));
    const proxy = spawn(process.execPath, [...IDLE, '--', path.join(profile, 'chrome')], { stdio: 'ignore', detached: true });
    spawned.push(proxy);
    recordProxyPid(profile, proxy.pid);
    return { profile, proxy };
}

function startReaper(profile, runnerPid) {
    const reaper = spawn(process.execPath, [REAPER], {
        stdio: 'ignore',
        env: { ...process.env, LIVE_REAPER_PROFILE: profile, LIVE_REAPER_RUNNER: String(runnerPid), LIVE_REAPER_STARTED: String(Date.now()) },
    });
    spawned.push(reaper);
    return reaper;
}

test('a runner killed with SIGKILL gets its proxy stopped and its profile removed', async () => {
    const { profile, proxy } = sandbox();
    const runner = spawn(process.execPath, IDLE, { stdio: 'ignore' });
    spawned.push(runner);
    startReaper(profile, runner.pid);

    await sleep(2500);
    assert.ok(alive(proxy.pid) && fs.existsSync(profile), 'nothing may be torn down while the runner lives');

    runner.kill('SIGKILL');
    assert.ok(await waitFor(() => !alive(proxy.pid)), 'the proxy must be stopped');
    assert.ok(await waitFor(() => !fs.existsSync(profile)), 'the profile must be removed');
});

test('a sandbox the runner already stopped is left alone and the watchdog exits', async () => {
    const { profile, proxy } = sandbox();
    fs.writeFileSync(path.join(profile, STOPPED_MARKER), '');
    const gone = spawn(process.execPath, IDLE, { stdio: 'ignore' });
    spawned.push(gone);
    gone.kill('SIGKILL');
    await new Promise((resolve) => gone.once('exit', resolve));

    const reaper = startReaper(profile, gone.pid);
    await new Promise((resolve) => reaper.once('exit', resolve));
    assert.ok(alive(proxy.pid) && fs.existsSync(profile), 'the marker means the runner owns the teardown');
});

test('teardown never signals a pid whose command line is not this sandbox', () => {
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'chrome-agent-live-'));
    profiles.push(profile);
    const bystander = spawn(process.execPath, IDLE, { stdio: 'ignore' });
    spawned.push(bystander);
    recordProxyPid(profile, bystander.pid);

    removeSandbox({ profile, startedAt: Date.now() });
    assert.ok(alive(bystander.pid), 'a reused pid must not be terminated');
    assert.equal(fs.existsSync(profile), false);
});
