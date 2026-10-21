// @vitest-environment node
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { BaseUnavailableError, introducedOrphans, materializeBase } from '../orphan-modules-base';

const CONSUMER_EXTENSIONS: ReadonlySet<string> = new Set(['.ts', '.mjs', '.cjs', '.js']);
const DIRECTORIES = ['src', 'scripts'];
const scratchDirs: string[] = [];

function scratch(): string {
  const dir = mkdtempSync(join(tmpdir(), 'orphan-base-test-'));
  scratchDirs.push(dir);
  return dir;
}

function git(cwd: string, ...args: string[]): void {
  execFileSync(
    'git',
    ['-c', 'user.name=test', '-c', 'user.email=test@example.com', '-c', 'commit.gpgsign=false', ...args],
    { cwd, stdio: 'pipe' },
  );
}

function commitAll(repo: string, message: string): void {
  git(repo, 'add', '-A');
  git(repo, 'commit', '-m', message);
}

function write(root: string, files: Record<string, string>): void {
  for (const [path, content] of Object.entries(files)) {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), content);
  }
}

/** main 上提交 `baseFiles`，再从它分出 feature 分支并提交 `featureFiles`，返回仓库根（HEAD 在 feature 上）。 */
function repoWithFeatureBranch(
  baseFiles: Record<string, string>,
  featureFiles: Record<string, string>,
  subdirectory = '',
): string {
  const repo = scratch();
  git(repo, 'init', '-b', 'main');
  write(join(repo, subdirectory), baseFiles);
  commitAll(repo, 'base');
  git(repo, 'checkout', '-b', 'feature');
  write(join(repo, subdirectory), featureFiles);
  commitAll(repo, 'feature');
  return repo;
}

function materialize(projectRoot: string, rev: string): { base: string; destination: string } {
  const destination = scratch();
  const base = materializeBase({
    projectRoot,
    rev,
    destination,
    directories: DIRECTORIES,
    rootExtensions: CONSUMER_EXTENSIONS,
  });
  return { base, destination };
}

afterAll(() => {
  for (const dir of scratchDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

describe('introducedOrphans', () => {
  it('keeps only the orphans that were not orphans at the base', () => {
    expect(introducedOrphans(['a.ts', 'b.ts', 'c.ts'], ['b.ts', 'gone.ts'])).toEqual(['a.ts', 'c.ts']);
  });

  it('reports nothing when every current orphan already was one', () => {
    expect(introducedOrphans(['a.ts'], ['a.ts', 'b.ts'])).toEqual([]);
  });

  it('reports every orphan when the base had none', () => {
    expect(introducedOrphans(['a.ts', 'b.ts'], [])).toEqual(['a.ts', 'b.ts']);
  });
});

describe('materializeBase', () => {
  const baseFiles = {
    'src/lib/a.ts': 'export const a = 1;',
    'scripts/gate.mjs': "import '../src/lib/a.ts';",
    'next.config.ts': "export default { plugin: './src/lib/a.ts' };",
    'env.d.ts': 'declare const x: number;',
    'package.json': '{}',
    'README.md': 'docs',
  };
  const featureFiles = { 'src/lib/a.ts': 'export const a = 2;', 'src/lib/new.ts': 'export const n = 1;' };
  // 只读用例共用一个仓库：建仓是这个文件里最贵的步骤。
  let shared: string;
  beforeAll(() => {
    shared = repoWithFeatureBranch(baseFiles, featureFiles);
  });

  it('writes the merge-base scan inputs: source directories and root build configs only', () => {
    const { base, destination } = materialize(shared, 'main');
    expect(base).toMatch(/^[0-9a-f]{40}$/);
    expect(readFileSync(join(destination, 'src/lib/a.ts'), 'utf8')).toBe('export const a = 1;');
    expect(existsSync(join(destination, 'src/lib/new.ts'))).toBe(false);
    expect(existsSync(join(destination, 'scripts/gate.mjs'))).toBe(true);
    expect(existsSync(join(destination, 'next.config.ts'))).toBe(true);
    expect(existsSync(join(destination, 'env.d.ts'))).toBe(false);
    expect(existsSync(join(destination, 'package.json'))).toBe(false);
    expect(existsSync(join(destination, 'README.md'))).toBe(false);
  });

  it('compares against the merge-base, not the tip of the reference revision', () => {
    const repo = repoWithFeatureBranch(baseFiles, featureFiles);
    git(repo, 'checkout', 'main');
    write(repo, { 'src/lib/moved-on.ts': 'export const m = 1;' });
    commitAll(repo, 'main moves on');
    git(repo, 'checkout', 'feature');
    const { destination } = materialize(repo, 'main');
    expect(existsSync(join(destination, 'src/lib/moved-on.ts'))).toBe(false);
    expect(readFileSync(join(destination, 'src/lib/a.ts'), 'utf8')).toBe('export const a = 1;');
  });

  it('resolves paths relative to the project when it lives in a repository subdirectory', () => {
    const repo = repoWithFeatureBranch(baseFiles, featureFiles, 'web');
    const { destination } = materialize(join(repo, 'web'), 'main');
    expect(readFileSync(join(destination, 'src/lib/a.ts'), 'utf8')).toBe('export const a = 1;');
    expect(existsSync(join(destination, 'next.config.ts'))).toBe(true);
  });

  it('fails closed on a revision that does not exist', () => {
    expect(() => materialize(shared, 'no-such-ref')).toThrow(BaseUnavailableError);
  });

  it('rejects a revision that looks like a git option', () => {
    expect(() => materialize(shared, '--output=/tmp/should-not-exist')).toThrow(BaseUnavailableError);
  });

  it('fails closed outside a git repository', () => {
    expect(() => materialize(scratch(), 'main')).toThrow(BaseUnavailableError);
  });

  it('fails closed when the base lacks a scanned directory', () => {
    const repo = repoWithFeatureBranch({ 'src/lib/a.ts': 'export {};' }, { 'scripts/new.mjs': 'export {};' });
    expect(() => materialize(repo, 'main')).toThrow(BaseUnavailableError);
  });

  it('fails closed when the histories share no common ancestor', () => {
    const repo = repoWithFeatureBranch(baseFiles, featureFiles);
    git(repo, 'checkout', '--orphan', 'unrelated');
    write(repo, { 'src/lib/u.ts': 'export {};' });
    commitAll(repo, 'unrelated root');
    expect(() => materialize(repo, 'main')).toThrow(BaseUnavailableError);
  });
});
