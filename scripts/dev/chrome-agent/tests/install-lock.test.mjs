// The installer's mkdir lock must be fully released (pid file included), otherwise every install
// leaves a stale lock behind, and it must still be taken over from a dead holder.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { after, test } from 'node:test';
import { fileURLToPath } from 'node:url';

const LIB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../lib-chrome-agent.sh');
const base = fs.mkdtempSync(path.join(os.tmpdir(), 'chrome-agent-lock-test-'));
const lockDir = path.join(base, '.install.lock');
after(() => fs.rmSync(base, { recursive: true, force: true }));

const bash = (script) => execFileSync('bash', ['-c', `source "${LIB}"; ${script}`], {
    env: { ...process.env, MYRM_CHROME_AGENT_INSTALL_DIR: base },
});

test('release removes the lock directory, pid file included', () => {
    bash('chrome_agent_lock_acquire; chrome_agent_lock_release');
    assert.equal(fs.existsSync(lockDir), false);
});

test('a lock left by a dead holder is taken over and then released', () => {
    fs.mkdirSync(lockDir);
    fs.writeFileSync(path.join(lockDir, 'pid'), '99999999\n');
    bash('chrome_agent_lock_acquire; chrome_agent_lock_release');
    assert.equal(fs.existsSync(lockDir), false);
});
