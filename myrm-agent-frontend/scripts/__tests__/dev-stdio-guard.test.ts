// @vitest-environment node
import { type ChildProcess, spawn } from 'child_process';
import { transformSync } from 'esbuild';
import { EventEmitter } from 'events';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installDevStdioGuard } from '../dev-stdio-guard';

const GUARD_SOURCE = path.resolve(__dirname, '..', 'dev-stdio-guard.ts');
/** An unguarded process re-enters its handlers tens of thousands of times a second; a healthy one never does. */
const STORM_FLOOR = 1000;

let workDir: string;
const alive = new Set<ChildProcess>();

beforeEach(() => {
  workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dev-stdio-guard-'));
});

afterEach(() => {
  alive.forEach((child) => child.kill('SIGKILL'));
  alive.clear();
  fs.rmSync(workDir, { recursive: true, force: true });
});

const errno = (code?: string): NodeJS.ErrnoException =>
  Object.assign(new Error(`write ${code ?? 'failed'}`), code === undefined ? {} : { code });

const until = async (condition: () => boolean, label: string): Promise<void> => {
  const deadline = Date.now() + 10_000;
  while (!condition()) {
    if (Date.now() > deadline) {
      throw new Error(`timed out waiting for: ${label}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
};

describe('installDevStdioGuard (unit)', () => {
  it.each(['EPIPE', 'ECONNRESET', 'EIO', 'ENOSPC', undefined])('absorbs a %s error on either stream', (code) => {
    const streams = [new EventEmitter(), new EventEmitter()];
    expect(() => new EventEmitter().emit('error', errno(code))).toThrow();

    installDevStdioGuard(streams);

    for (const stream of streams) {
      expect(() => stream.emit('error', errno(code))).not.toThrow();
    }
  });

  it('adds one listener per stream however often it runs, including after next.config.ts is re-evaluated', async () => {
    const streams = [new EventEmitter(), new EventEmitter()];
    installDevStdioGuard(streams);
    installDevStdioGuard(streams);
    vi.resetModules();
    const reloaded = await import('../dev-stdio-guard');
    reloaded.installDevStdioGuard(streams);

    expect(streams.map((stream) => stream.listenerCount('error'))).toEqual([1, 1]);
  });
});

describe('installDevStdioGuard (real processes)', () => {
  /** The guard as a CommonJS file a child process can load; the child is plain node, as Next's server is. */
  function compileGuard(): string {
    const { code } = transformSync(fs.readFileSync(GUARD_SOURCE, 'utf8'), {
      loader: 'ts',
      format: 'cjs',
      platform: 'node',
      target: 'node18',
    });
    const file = path.join(workDir, 'dev-stdio-guard.cjs');
    fs.writeFileSync(file, code);
    return file;
  }

  /**
   * Handlers shaped like the ones Next registers on its server process (one synchronous, one deferred
   * through the event loop, both logging through the stdio that just failed), plus a request log on
   * stdout and a warning on stderr.
   */
  function childProgram(guarded: boolean): string {
    return `
      const fs = require('fs');
      const counterFile = process.argv[1];
      let handled = 0;
      let writes = 0;
      process.on('uncaughtException', (error) => { handled += 1; console.error('uncaughtException: ', error.code); });
      process.on('uncaughtException', async (error) => {
        await new Promise((resolve) => setImmediate(resolve));
        handled += 1;
        console.error('uncaughtException', error.code);
      });
      ${guarded ? `require(${JSON.stringify(compileGuard())}).installDevStdioGuard();` : ''}
      setInterval(() => fs.writeFileSync(counterFile, JSON.stringify({ handled, writes })), 25);
      process.stdin.on('data', () => {
        process.stdout.write('GET / 200\\n');
        process.stderr.write('slow request\\n');
        writes += 1;
      });
      console.log('ready');
    `;
  }

  /** Starts the child, then closes the reading end of its stdout and stderr. */
  async function startWithGoneReader(guarded: boolean) {
    const counterFile = path.join(workDir, 'counters.json');
    const child = spawn(process.execPath, ['-e', childProgram(guarded), counterFile], {
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    alive.add(child);
    await new Promise<void>((resolve) => child.stdout.once('data', () => resolve()));
    child.stdout.destroy();
    child.stderr.destroy();
    await new Promise((resolve) => setTimeout(resolve, 100));
    const counters = (): { handled: number; writes: number } => {
      try {
        return JSON.parse(fs.readFileSync(counterFile, 'utf8'));
      } catch {
        return { handled: 0, writes: 0 };
      }
    };
    return { child, counters };
  }

  it('without the guard one write to a gone reader sends the process into an uncaught-exception loop', async () => {
    const { child, counters } = await startWithGoneReader(false);

    child.stdin.write('request\n');
    await until(() => counters().handled >= STORM_FLOOR, 'the uncaughtException handlers to be re-entered');

    expect(child.exitCode).toBeNull();
  });

  it('with the guard the process logs on into a gone reader without an exception, a loop or an exit', async () => {
    const { child, counters } = await startWithGoneReader(true);

    for (let request = 0; request < 4; request += 1) {
      child.stdin.write('request\n');
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    await until(() => counters().writes >= 4, 'every request to have been logged');
    await new Promise((resolve) => setTimeout(resolve, 300));

    expect(counters().handled).toBe(0);
    expect(child.exitCode).toBeNull();
    expect(child.signalCode).toBeNull();
  });

  it('leaves the output of a process alone whose stdout and stderr are regular files, as under the managed dev stack', async () => {
    const logFile = path.join(workDir, 'frontend.log');
    const fd = fs.openSync(logFile, 'a');
    const program = `
      require(${JSON.stringify(compileGuard())}).installDevStdioGuard();
      for (let line = 0; line < 50; line += 1) {
        process.stdout.write('out ' + line + '\\n');
        process.stderr.write('err ' + line + '\\n');
      }
    `;
    const child = spawn(process.execPath, ['-e', program], { stdio: ['ignore', fd, fd] });
    alive.add(child);
    const code = await new Promise<number | null>((resolve) => child.once('exit', (exitCode) => resolve(exitCode)));
    fs.closeSync(fd);

    expect(code).toBe(0);
    expect(fs.readFileSync(logFile, 'utf8').trim().split('\n')).toHaveLength(100);
  });
});
