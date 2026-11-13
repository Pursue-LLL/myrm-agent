// @vitest-environment node
import { spawnSync } from 'child_process';
import { transformSync } from 'esbuild';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { enforceSupervisedDev, isSupervised, SUPERVISOR_PRELOAD } from '../dev-supervision-gate';

const FRONTEND_ROOT = path.resolve(__dirname, '..', '..');
const GATE_SOURCE = path.join(FRONTEND_ROOT, 'scripts', 'dev-supervision-gate.ts');
const CONTEXT = 'next dev (unit)';
const PRELOAD_PATH = `/repo/myrm-agent-frontend/scripts/${SUPERVISOR_PRELOAD}`;

class Exited extends Error {
  constructor(readonly code: number) {
    super(`exit ${code}`);
  }
}

const exitWithCode = (code: number): never => {
  throw new Exited(code);
};

let workDir: string;

beforeEach(() => {
  workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dev-supervision-gate-'));
});

afterEach(() => {
  vi.restoreAllMocks();
  fs.rmSync(workDir, { recursive: true, force: true });
});

describe('isSupervised', () => {
  it.each([
    ['the Next CLI, which carries the preload in its own execArgv', ['--require', PRELOAD_PATH], undefined],
    [
      'the server worker, which gets it through NODE_OPTIONS',
      [],
      `--require=${PRELOAD_PATH} --max-old-space-size=8192`,
    ],
    [
      'a worker whose preload path has to be quoted',
      [],
      `--require="/my repo/scripts/${SUPERVISOR_PRELOAD}" --enable-source-maps`,
    ],
  ])('recognises %s', (_label, execArgv, nodeOptions) => {
    expect(isSupervised({ execArgv, nodeOptions })).toBe(true);
  });

  it.each([
    ['a bare launch', [], undefined],
    ['an empty NODE_OPTIONS', [], ''],
    ['unrelated node flags', ['--inspect'], '--max-old-space-size=8192 --enable-source-maps'],
    ['some other preload', ['--require', '/repo/scripts/other-gate.cjs'], '--require=/repo/scripts/other-gate.cjs'],
  ])('does not take %s for supervised', (_label, execArgv, nodeOptions) => {
    expect(isSupervised({ execArgv, nodeOptions })).toBe(false);
  });
});

describe('enforceSupervisedDev (unit)', () => {
  it('lets a supervised process through without a word', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const exit = vi.fn(exitWithCode);

    enforceSupervisedDev({ context: CONTEXT, execArgv: ['--require', PRELOAD_PATH], nodeOptions: '', exit });

    expect(exit).not.toHaveBeenCalled();
    expect(error).not.toHaveBeenCalled();
  });

  it('refuses a process nobody supervises with exit code 1', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    expect(() => enforceSupervisedDev({ context: CONTEXT, execArgv: [], nodeOptions: '', exit: exitWithCode })).toThrow(
      new Exited(1),
    );
  });

  it('names what it refuses and how to start the server properly', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    expect(() => enforceSupervisedDev({ context: CONTEXT, execArgv: [], nodeOptions: '', exit: exitWithCode })).toThrow(
      Exited,
    );

    const message = error.mock.calls.map((call) => call.join(' ')).join('\n');
    expect(message).toContain(`Refusing ${CONTEXT}`);
    expect(message).toContain(`no ${SUPERVISOR_PRELOAD} preload`);
    expect(message).toContain('MYRM_FRONTEND_PORT=<port> bun run dev');
  });
});

describe('enforceSupervisedDev (real processes)', () => {
  /** The gate as a CommonJS file a child process can load; the child is plain node, as Next's server is. */
  function compileGate(): string {
    const { code } = transformSync(fs.readFileSync(GATE_SOURCE, 'utf8'), {
      loader: 'ts',
      format: 'cjs',
      platform: 'node',
      target: 'node18',
    });
    const file = path.join(workDir, 'dev-supervision-gate.cjs');
    fs.writeFileSync(file, code);
    return file;
  }

  /** Stands in for next-dev-gate.cjs: node only has to find a preload of that name on the command line. */
  function stubPreload(): string {
    const file = path.join(workDir, SUPERVISOR_PRELOAD);
    fs.writeFileSync(file, "'use strict';\n");
    return file;
  }

  /** Runs the gate as the first thing a server process does, then prints a line only the server code would. */
  function startServer(nodeArgs: string[], env: Record<string, string>) {
    const program = `
      require(${JSON.stringify(compileGate())}).enforceSupervisedDev({ context: 'next dev (child)' });
      console.log('server code reached');
    `;
    return spawnSync(process.execPath, [...nodeArgs, '-e', program], {
      env: { PATH: process.env.PATH, ...env },
      encoding: 'utf8',
      timeout: 20_000,
    });
  }

  it('stops a raw launch before any server code runs', () => {
    const result = startServer([], {});

    expect(result.status).toBe(1);
    expect(result.stdout).not.toContain('server code reached');
    expect(result.stderr).toContain('Refusing next dev (child)');
    expect(result.stderr).toContain('bun run dev');
  });

  it('lets through a process started the way dev.ts starts Next: node --require <preload>', () => {
    const result = startServer(['--require', stubPreload()], {});

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('server code reached');
    expect(result.stderr).toBe('');
  });

  it('lets through the server worker, which Next starts with the preload in NODE_OPTIONS only', () => {
    const result = startServer([], { NODE_OPTIONS: `--require=${stubPreload()} --max-old-space-size=512` });

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('server code reached');
    expect(result.stderr).toBe('');
  });
});

describe('wiring', () => {
  const read = (...segments: string[]): string => fs.readFileSync(path.join(FRONTEND_ROOT, ...segments), 'utf8');

  it('next.config.ts enforces it in the development branch only, so builds and production starts are never refused', () => {
    const source = read('next.config.ts');
    const developmentBranch =
      /if \(process\.env\.NODE_ENV === 'development'\) \{([\s\S]*?)\n\}/.exec(source)?.[1] ?? '';

    expect(developmentBranch).toMatch(/enforceSupervisedDev\(\s*\{[^}]*\}\s*\)/);
    expect(source.match(/enforceSupervisedDev\(/g)).toHaveLength(1);
  });

  it('dev.ts starts Next with the preload this gate looks for', () => {
    const source = read('scripts', 'dev.ts');

    expect(source).toContain(`path.join(__dirname, '${SUPERVISOR_PRELOAD}')`);
    expect(source).toMatch(/\['--require', preloadGate,/);
    expect(fs.existsSync(path.join(FRONTEND_ROOT, 'scripts', SUPERVISOR_PRELOAD))).toBe(true);
  });
});
