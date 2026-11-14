// @vitest-environment node
import { spawnSync } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ensureDevPython, probePython, resolveDevPython, type ProbePython } from '../python-runtime';

let root: string;

/** The frontend checkout; its sibling `myrm-agent-server` is where the venv lives. */
const frontendRoot = (): string => path.join(root, 'myrm-agent-frontend');
const venvPython = (): string => path.join(root, 'myrm-agent-server', '.venv', 'bin', 'python');

/** A file at `file` that exits with `status` when run; returns the path. */
function makeExecutable(file: string, status = 0): string {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `#!/bin/sh\nexit ${status}\n`, { mode: 0o755 });
  return file;
}

/** A version check that passes only the listed files and remembers every file it was asked about, in order. */
function versionCheck(...accepted: string[]): { probe: ProbePython; tried: string[] } {
  const tried: string[] = [];
  return {
    probe: (file) => {
      tried.push(file);
      return accepted.includes(file);
    },
    tried,
  };
}

/** PATH made of the named directories under the scratch root. */
const pathOf = (...names: string[]): string => names.map((name) => path.join(root, name)).join(path.delimiter);

beforeEach(() => {
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'python-runtime-'));
});

afterEach(() => {
  fs.rmSync(root, { recursive: true, force: true });
});

describe('resolveDevPython', () => {
  it('prefers the server venv interpreter', () => {
    const venv = makeExecutable(venvPython());
    const onPath = makeExecutable(path.join(root, 'bin', 'python3.13'));
    const { probe, tried } = versionCheck(venv, onPath);

    const found = resolveDevPython({ frontendRoot: frontendRoot(), envPath: pathOf('bin'), probe });

    expect(found).toBe(venv);
    expect(tried).toEqual([venv]);
  });

  it('passes over a venv interpreter that is too old', () => {
    const venv = makeExecutable(venvPython());
    const onPath = makeExecutable(path.join(root, 'bin', 'python3.12'));
    const { probe, tried } = versionCheck(onPath);

    const found = resolveDevPython({ frontendRoot: frontendRoot(), envPath: pathOf('bin'), probe });

    expect(found).toBe(onPath);
    expect(tried).toEqual([venv, onPath]);
  });

  it('tries a versioned name anywhere on PATH before a bare python3 that comes earlier', () => {
    const bare = makeExecutable(path.join(root, 'first', 'python3'));
    const versioned = makeExecutable(path.join(root, 'second', 'python3.13'));
    const { probe, tried } = versionCheck(bare, versioned);

    const found = resolveDevPython({ frontendRoot: frontendRoot(), envPath: pathOf('first', 'second'), probe });

    expect(found).toBe(versioned);
    expect(tried).toEqual([versioned]);
  });

  it('skips a python3 that is too old and takes a newer one further along PATH', () => {
    const system = makeExecutable(path.join(root, 'usr-bin', 'python3'));
    const modern = makeExecutable(path.join(root, 'homebrew', 'python3'));
    const { probe, tried } = versionCheck(modern);

    const found = resolveDevPython({ frontendRoot: frontendRoot(), envPath: pathOf('usr-bin', 'homebrew'), probe });

    expect(found).toBe(modern);
    expect(tried).toEqual([system, modern]);
  });

  it('only runs candidates that exist', () => {
    const { probe, tried } = versionCheck();

    const found = resolveDevPython({ frontendRoot: frontendRoot(), envPath: pathOf('nowhere'), probe });

    expect(found).toBeNull();
    expect(tried).toEqual([]);
  });

  it('finds nothing when no candidate qualifies or PATH is unset', () => {
    makeExecutable(venvPython());
    makeExecutable(path.join(root, 'bin', 'python3'));
    const { probe } = versionCheck();

    expect(resolveDevPython({ frontendRoot: frontendRoot(), envPath: pathOf('bin'), probe })).toBeNull();
    expect(resolveDevPython({ frontendRoot: frontendRoot(), envPath: undefined, probe })).toBeNull();
  });
});

describe('ensureDevPython', () => {
  it('returns the interpreter without a word when one qualifies', () => {
    const onPath = makeExecutable(path.join(root, 'bin', 'python3.13'));
    const warnings: string[] = [];

    const found = ensureDevPython({
      frontendRoot: frontendRoot(),
      envPath: pathOf('bin'),
      probe: versionCheck(onPath).probe,
      warn: (message) => warnings.push(message),
    });

    expect(found).toBe(onPath);
    expect(warnings).toEqual([]);
  });

  it('falls back to python3 and says at launch that the guard cannot run', () => {
    makeExecutable(path.join(root, 'bin', 'python3'));
    const warnings: string[] = [];

    const found = ensureDevPython({
      frontendRoot: frontendRoot(),
      envPath: pathOf('bin'),
      probe: versionCheck().probe,
      warn: (message) => warnings.push(message),
    });

    expect(found).toBe('python3');
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain('FOOTPRINT_GUARD_OFF');
    expect(warnings[0]).toContain('3.11');
  });
});

describe('probePython', () => {
  it('reads the exit status of the version check', () => {
    expect(probePython(makeExecutable(path.join(root, 'new'), 0))).toBe(true);
    expect(probePython(makeExecutable(path.join(root, 'old'), 1))).toBe(false);
  });

  it('treats a file that cannot be run as unusable', () => {
    expect(probePython(path.join(root, 'missing'))).toBe(false);
  });

  const python3 = spawnSync('python3', ['-c', 'import sys; print(*sys.version_info[:2])'], { encoding: 'utf8' });

  // The version check is Python source, so only a real interpreter proves it.
  it.skipIf(python3.status !== 0)('agrees with what the local python3 reports about itself', () => {
    const [major, minor] = python3.stdout.trim().split(' ').map(Number);

    expect(probePython('python3')).toBe(major > 3 || (major === 3 && minor >= 11));
  });
});
