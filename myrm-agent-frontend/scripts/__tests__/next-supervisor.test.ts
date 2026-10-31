// @vitest-environment node
import { type ChildProcess, spawn } from 'child_process';
import path from 'path';
import { afterEach, describe, expect, it } from 'vitest';
import { type FootprintProbe, type FootprintReading, footprintProbe, superviseNext } from '../next-supervisor';

const LIB_DIR = path.resolve(__dirname, '..', '..', '..', 'scripts', 'dev', 'lib');
const BACKEND_PYTHON = path.resolve(__dirname, '..', '..', '..', 'myrm-agent-server', '.venv', 'bin', 'python');
const IDLE = ['-e', 'setInterval(() => {}, 1000)'];

const OK: FootprintReading = { verdict: 'ok', line: 'FOOTPRINT pid=1 procs=1 mb=100 limit_mb=10240' };
const EXCEEDED: FootprintReading = { verdict: 'exceeded', line: 'FOOTPRINT pid=1 procs=1 mb=20000 limit_mb=10240' };
const UNMEASURABLE: FootprintReading = { verdict: 'unmeasurable', line: '' };

const alive = new Set<ChildProcess>();
afterEach(() => {
  alive.forEach((child) => child.kill('SIGKILL'));
  alive.clear();
});

function idleChild(): ChildProcess {
  const child = spawn(process.execPath, IDLE, { stdio: 'ignore' });
  alive.add(child);
  return child;
}

function scripted(readings: FootprintReading[]): FootprintProbe {
  let index = 0;
  return async () => readings[Math.min(index++, readings.length - 1)];
}

const until = async (condition: () => boolean, label: string): Promise<void> => {
  const deadline = Date.now() + 8000;
  while (!condition()) {
    if (Date.now() > deadline) {
      throw new Error(`timed out waiting for: ${label}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
};

interface Harness {
  spawned: ChildProcess[];
  logs: string[];
  respawns: number;
  exits: Array<number | null>;
}

function supervise(probe: FootprintProbe, breaker = { max: 2, windowMs: 60_000 }) {
  const harness: Harness = { spawned: [], logs: [], respawns: 0, exits: [] };
  const supervisor = superviseNext({
    spawnChild: () => {
      const child = idleChild();
      harness.spawned.push(child);
      return child;
    },
    beforeRespawn: () => {
      harness.respawns += 1;
    },
    probe,
    onExit: (code) => harness.exits.push(code),
    onSpawnError: (error) => {
      throw error;
    },
    intervalMs: 10,
    killGraceMs: 2000,
    breaker,
    log: (message) => harness.logs.push(message),
  });
  return { harness, supervisor };
}

describe('superviseNext', () => {
  it('replaces a child whose footprint exceeds the limit, once the old one has exited', async () => {
    const { harness, supervisor } = supervise(scripted([OK, EXCEEDED, OK]));
    await until(() => harness.spawned.length === 2, 'second child');

    const [first, second] = harness.spawned;
    expect(first.exitCode !== null || first.signalCode !== null).toBe(true);
    expect(second.pid).not.toBe(first.pid);
    expect(supervisor.child).toBe(second);
    expect(harness.respawns).toBe(1);
    expect(harness.exits).toEqual([]);
    expect(harness.logs.some((line) => line.startsWith('FOOTPRINT_RESTART:'))).toBe(true);
    supervisor.stop();
  });

  it('opens the breaker instead of restarting a third time in the window', async () => {
    const { harness, supervisor } = supervise(scripted([EXCEEDED]));
    await until(() => harness.logs.some((line) => line.startsWith('FOOTPRINT_BREAKER_OPEN:')), 'breaker');

    expect(harness.spawned).toHaveLength(3);
    expect(harness.logs.filter((line) => line.startsWith('FOOTPRINT_RESTART:'))).toHaveLength(2);
    expect(supervisor.child.exitCode).toBeNull();
    supervisor.stop();
  });

  it('forgets restarts that fall outside the window', async () => {
    let clock = 0;
    const harness: Harness = { spawned: [], logs: [], respawns: 0, exits: [] };
    const supervisor = superviseNext({
      spawnChild: () => {
        const child = idleChild();
        harness.spawned.push(child);
        return child;
      },
      beforeRespawn: () => {
        harness.respawns += 1;
        clock += 120_000;
      },
      probe: scripted([EXCEEDED]),
      onExit: (code) => harness.exits.push(code),
      onSpawnError: (error) => {
        throw error;
      },
      intervalMs: 10,
      killGraceMs: 2000,
      breaker: { max: 1, windowMs: 60_000 },
      now: () => clock,
      log: (message) => harness.logs.push(message),
    });
    await until(() => harness.spawned.length === 4, 'third restart');

    expect(harness.logs.some((line) => line.startsWith('FOOTPRINT_BREAKER_OPEN:'))).toBe(false);
    supervisor.stop();
  });

  it('reports an exit it did not cause and never respawns', async () => {
    const { harness, supervisor } = supervise(scripted([OK]));
    await until(() => supervisor.child.pid !== undefined, 'child pid');
    supervisor.child.kill('SIGKILL');
    await until(() => harness.exits.length === 1, 'onExit');

    expect(harness.exits).toEqual([null]);
    expect(harness.spawned).toHaveLength(1);
    expect(harness.respawns).toBe(0);
  });

  it('does not respawn or report twice when stopped while a restart is in flight', async () => {
    const { harness, supervisor } = supervise(scripted([EXCEEDED]));
    await until(() => harness.logs.some((line) => line.startsWith('FOOTPRINT_RESTART:')), 'restart requested');
    supervisor.stop();
    await until(() => harness.exits.length === 1, 'onExit after stop');
    await new Promise((resolve) => setTimeout(resolve, 100));

    expect(harness.spawned).toHaveLength(1);
    expect(harness.exits).toHaveLength(1);
  });

  it('switches itself off after repeated unmeasurable samples and leaves the child alone', async () => {
    const { harness, supervisor } = supervise(scripted([UNMEASURABLE]));
    await until(() => harness.logs.some((line) => line.startsWith('FOOTPRINT_GUARD_OFF:')), 'guard off');

    expect(harness.spawned).toHaveLength(1);
    expect(supervisor.child.exitCode).toBeNull();
    supervisor.stop();
  });

  it('logs the first healthy reading so a boot always leaves a data point', async () => {
    const { harness, supervisor } = supervise(scripted([OK]));
    await until(() => harness.logs.length > 0, 'first reading');

    expect(harness.logs[0]).toBe(OK.line);
    supervisor.stop();
  });
});

describe('footprintProbe against the real frontend_lifecycle CLI', () => {
  const probe = footprintProbe({
    libDir: LIB_DIR,
    python: BACKEND_PYTHON,
    env: { ...process.env, MYRM_FRONTEND_FOOTPRINT_LIMIT_MB: '100000' },
  });
  const tight = footprintProbe({
    libDir: LIB_DIR,
    python: BACKEND_PYTHON,
    env: { ...process.env, MYRM_FRONTEND_FOOTPRINT_LIMIT_MB: '1' },
  });

  it('reads a live process as ok under a generous limit and exceeded under a 1 MB limit', async () => {
    const child = idleChild();
    await until(() => child.pid !== undefined, 'child pid');

    const generous = await probe(child.pid as number);
    expect(generous.verdict).toBe('ok');
    expect(generous.line).toMatch(/^FOOTPRINT pid=\d+ procs=\d+ mb=\d+ limit_mb=100000$/);

    const strict = await tight(child.pid as number);
    expect(strict.verdict).toBe('exceeded');
  });

  it('reads an interpreter that cannot import the package as unmeasurable, never as exceeded', async () => {
    const child = idleChild();
    const unusable = footprintProbe({ libDir: LIB_DIR, python: '/nonexistent/python' });

    expect((await unusable(child.pid as number)).verdict).toBe('unmeasurable');
  });

  it('reports a dead pid as unmeasurable', async () => {
    const child = idleChild();
    const pid = child.pid as number;
    child.kill('SIGKILL');
    await until(() => child.exitCode !== null || child.signalCode !== null, 'child exit');

    expect((await probe(pid)).verdict).toBe('unmeasurable');
  });
});
