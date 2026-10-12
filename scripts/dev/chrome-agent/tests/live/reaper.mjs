// Detached watchdog for one live-test sandbox. A test runner that is SIGKILLed (a tool timeout, the
// OOM killer) never runs its own cleanup, which would leave the proxy, its Chrome and the temp
// profile running forever. This process has its own process group, outlives the runner, and
// tears the sandbox down once the runner is gone.
//
// The sandbox is described through the environment, not argv: the teardown finds the sandbox's
// processes with `pgrep -f <profile>`, which would match this watchdog if the path were in argv.
import fs from 'node:fs';
import path from 'node:path';
import { removeSandbox, STOPPED_MARKER } from './sandbox-cleanup.mjs';

const profile = process.env.LIVE_REAPER_PROFILE;
const runnerPid = Number(process.env.LIVE_REAPER_RUNNER);
const startedAt = Number(process.env.LIVE_REAPER_STARTED);
if (!profile || !runnerPid) process.exit(2);

const alive = (pid) => {
    try {
        process.kill(pid, 0);
        return true;
    } catch (err) {
        return err.code === 'EPERM';
    }
};
/** The runner cleaned up after itself (or the profile is gone): nothing left to watch. */
const finished = () => !fs.existsSync(profile) || fs.existsSync(path.join(profile, STOPPED_MARKER));

setInterval(() => {
    if (finished()) process.exit(0);
    if (alive(runnerPid)) return;
    removeSandbox({ profile, startedAt });
    process.exit(0);
}, 1000);
