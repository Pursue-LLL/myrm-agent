// @vitest-environment node
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { LINT_GATES, runGates } from '../run-lint-gates';

const packageScripts: Record<string, string> = JSON.parse(
  readFileSync(fileURLToPath(new URL('../../package.json', import.meta.url)), 'utf8'),
).scripts;

describe('runGates', () => {
  it('returns nothing when every gate passes', () => {
    expect(runGates(['a', 'b'], () => 0)).toEqual([]);
  });

  it('keeps running after a failure so one red gate cannot hide the others', () => {
    const executed: string[] = [];
    const failed = runGates(['a', 'b', 'c', 'd'], (script) => {
      executed.push(script);
      return script === 'a' || script === 'c' ? 1 : 0;
    });
    expect(executed).toEqual(['a', 'b', 'c', 'd']);
    expect(failed).toEqual(['a', 'c']);
  });

  it('treats any non-zero exit code as a failure', () => {
    expect(runGates(['a'], () => 2)).toEqual(['a']);
  });
});

describe('LINT_GATES', () => {
  it('only names scripts that exist in package.json', () => {
    for (const script of LINT_GATES) {
      expect(packageScripts[script], `missing package.json script "${script}"`).toBeDefined();
    }
  });

  it('is what `bun run lint` executes, so local runs and CI cannot drift apart', () => {
    expect(packageScripts.lint).toBe('bun scripts/run-lint-gates.ts');
  });

  it('lists each gate once', () => {
    expect(new Set(LINT_GATES).size).toBe(LINT_GATES.length);
  });
});
