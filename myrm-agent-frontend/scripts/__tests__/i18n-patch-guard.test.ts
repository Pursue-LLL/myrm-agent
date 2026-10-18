// @vitest-environment node
import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';

// 补丁应用器 + 修剪器都直接改 `locales/*.json`，所以每个用例都在临时仓库里跑**脚本的副本**：
// 脚本从自身位置推导 rootDir，只有副本才会把写入落在临时目录里。
// 若误用真实路径执行，脚本会按自己的 rootDir 覆盖真实 locale 文件 —— 末尾的
// "never touches the repository locales" 用例正是为这类错误加的回归保护。

const repoRoot = resolve(__dirname, '..', '..');
const scriptsDir = resolve(repoRoot, 'scripts');
const LOCALES = ['en', 'de', 'ja', 'ko', 'zh', 'zh-TW'] as const;

/** 运行前记录真实 locale 内容，供末尾的回归用例比对。 */
const repoLocalesBefore = new Map(LOCALES.map((l) => [l, readFileSync(join(repoRoot, 'locales', `${l}.json`))]));

const scratchDirs: string[] = [];

function scratch(): string {
  const dir = mkdtempSync(join(tmpdir(), 'i18n-patch-test-'));
  scratchDirs.push(dir);
  return dir;
}

afterAll(() => {
  for (const dir of scratchDirs) {
    rmSync(dir, { recursive: true, force: true });
  }
});

/**
 * 临时仓库：真实 en/目标 locale 的副本 + 目标 locale 的空补丁目录 + 脚本副本。
 * 不链接真实补丁目录，避免任何一个用例（或脚本自身的写入）碰到仓库文件。
 */
function sandbox(locale: string, ...scriptNames: string[]): string {
  const root = scratch();
  mkdirSync(join(root, 'locales'), { recursive: true });
  mkdirSync(join(root, 'scripts', 'translation-patches', locale), { recursive: true });
  for (const name of ['en', locale]) {
    writeFileSync(join(root, 'locales', `${name}.json`), readFileSync(join(repoRoot, 'locales', `${name}.json`)));
  }
  for (const name of scriptNames) {
    writeFileSync(join(root, 'scripts', name), readFileSync(join(scriptsDir, name)));
  }
  return root;
}

function writePatch(root: string, locale: string, file: string, tree: unknown): void {
  writeFileSync(join(root, 'scripts', 'translation-patches', locale, file), JSON.stringify(tree, null, 2) + '\n');
}

function run(root: string, args: string[]): { status: number; output: string } {
  try {
    const stdout = execFileSync('node', args, { cwd: root, encoding: 'utf8', stdio: 'pipe' });
    return { status: 0, output: stdout };
  } catch (error) {
    const failure = error as { status?: number; stdout?: string; stderr?: string };
    return { status: failure.status ?? 1, output: `${failure.stdout ?? ''}${failure.stderr ?? ''}` };
  }
}

describe('i18n-patch-apply structural guard', () => {
  it('refuses to replace an existing object subtree with a single leaf', () => {
    // `cron.schedule` is an object in en; a patch that writes it as "일정" would delete the whole subtree.
    const root = sandbox('ko', 'i18n-patch-apply.mjs');
    writePatch(root, 'ko', 'clobber.json', { cron: { schedule: '일정' } });

    const before = readFileSync(join(root, 'locales', 'ko.json'), 'utf8');
    const result = run(root, ['scripts/i18n-patch-apply.mjs', 'ko']);

    expect(result.status).toBe(1);
    expect(result.output).toContain('cron.schedule');
    expect(result.output).toContain('object subtree');
    expect(readFileSync(join(root, 'locales', 'ko.json'), 'utf8')).toBe(before);
  });

  it('refuses a key that is absent from the en SSOT', () => {
    const root = sandbox('zh', 'i18n-patch-apply.mjs');
    writePatch(root, 'zh', 'orphan.json', { checkpoint: { resumable: '可恢复' } });

    const before = readFileSync(join(root, 'locales', 'zh.json'), 'utf8');
    const result = run(root, ['scripts/i18n-patch-apply.mjs', 'zh']);

    expect(result.status).toBe(1);
    expect(result.output).toContain('checkpoint.resumable');
    expect(result.output).toContain('key SSOT');
    expect(readFileSync(join(root, 'locales', 'zh.json'), 'utf8')).toBe(before);
  });

  it('fills a key that is still the English SSOT value', () => {
    // A key the target language has not translated yet (still the en value) is what a patch exists to fill.
    const root = sandbox('zh', 'i18n-patch-apply.mjs');
    const en = JSON.parse(readFileSync(join(repoRoot, 'locales', 'en.json'), 'utf8'));
    const livePath = join(root, 'locales', 'zh.json');
    const live = JSON.parse(readFileSync(livePath, 'utf8'));
    live.cron.schedule.title = en.cron.schedule.title;
    writeFileSync(livePath, JSON.stringify(live, null, 2) + '\n');
    writePatch(root, 'zh', 'valid.json', { cron: { schedule: { title: '日程' } } });

    const result = run(root, ['scripts/i18n-patch-apply.mjs', 'zh']);

    expect(result.status).toBe(0);
    expect(JSON.parse(readFileSync(livePath, 'utf8')).cron.schedule.title).toBe('日程');
  });

  it('keeps an existing translation instead of regressing it to the patch snapshot', () => {
    // `Goal.verifications` is "Tests" in en; a stale patch carrying that English value must not
    // overwrite the live German "Prüfungen" — replaying a snapshot is content filling, not reverting.
    const root = sandbox('de', 'i18n-patch-apply.mjs');
    writePatch(root, 'de', 'stale.json', { Goal: { verifications: 'Tests' } });

    const before = JSON.parse(readFileSync(join(root, 'locales', 'de.json'), 'utf8')).Goal.verifications;
    const result = run(root, ['scripts/i18n-patch-apply.mjs', 'de']);

    expect(result.status).toBe(0);
    const after = JSON.parse(readFileSync(join(root, 'locales', 'de.json'), 'utf8')).Goal.verifications;
    expect(after).toBe(before);
    expect(after).not.toBe('Tests');
    expect(result.output).toContain('保留已有译文');
  });

  it('adds a whole subtree only when every leaf exists in the en SSOT', () => {
    const root = sandbox('zh', 'i18n-patch-apply.mjs');
    writePatch(root, 'zh', 'fresh.json', { cron: { schedule: { weekdayListAt: '{days} 于 {time}' } } });
    // Drop the live subtree so the patch takes the "add a missing subtree" branch.
    const live = JSON.parse(readFileSync(join(root, 'locales', 'zh.json'), 'utf8'));
    delete live.cron.schedule;
    writeFileSync(join(root, 'locales', 'zh.json'), JSON.stringify(live, null, 2) + '\n');

    const result = run(root, ['scripts/i18n-patch-apply.mjs', 'zh']);

    expect(result.status).toBe(0);
    expect(JSON.parse(readFileSync(join(root, 'locales', 'zh.json'), 'utf8')).cron.schedule.weekdayListAt).toBe(
      '{days} 于 {time}',
    );
  });
});

describe('i18n-prune-patch-keys', () => {
  it('drops stale keys and keeps valid ones, reporting before writing', () => {
    const root = sandbox('ja', 'i18n-prune-patch-keys.mjs');
    writePatch(root, 'ja', 'mixed.json', {
      cron: { schedule: { title: 'スケジュール' } },
      checkpoint: { resumable: '再開可能' },
    });

    const reported = run(root, ['scripts/i18n-prune-patch-keys.mjs', '--check']);
    expect(reported.status).toBe(1);
    expect(reported.output).toContain('checkpoint.resumable');
    // --check must not write.
    expect(
      JSON.parse(readFileSync(join(root, 'scripts', 'translation-patches', 'ja', 'mixed.json'), 'utf8')).checkpoint,
    ).toBeDefined();

    const applied = run(root, ['scripts/i18n-prune-patch-keys.mjs']);
    expect(applied.status).toBe(0);
    const pruned = JSON.parse(readFileSync(join(root, 'scripts', 'translation-patches', 'ja', 'mixed.json'), 'utf8'));
    expect(pruned.checkpoint).toBeUndefined();
    expect(pruned.cron.schedule.title).toBe('スケジュール');
  });
});

describe('sandbox isolation', () => {
  it('never touches the repository locales', () => {
    // Regression guard: running the real script path (instead of the sandbox copy) made the applier
    // resolve its own rootDir and overwrite locales/*.json in the working tree.
    for (const [locale, before] of repoLocalesBefore) {
      expect(readFileSync(join(repoRoot, 'locales', `${locale}.json`), 'utf8')).toBe(before.toString('utf8'));
    }
  });
});
