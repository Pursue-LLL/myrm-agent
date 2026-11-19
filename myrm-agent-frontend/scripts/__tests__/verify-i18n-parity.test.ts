// @vitest-environment node
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createContext } from '../verify-i18n/context.mjs';
import { verifyLocaleParity } from '../verify-i18n/locale-parity.mjs';

// 配置（allowlist）读真实 scripts/ 文件，locale 数据用内存合成。
const frontendRoot = fileURLToPath(new URL('../..', import.meta.url));

afterEach(() => {
  vi.restoreAllMocks();
});

function runParity(translations: Record<string, unknown>) {
  const ctx = createContext(frontendRoot);
  ctx.translations = translations;
  const error = vi.spyOn(console, 'error').mockImplementation(() => {});
  const log = vi.spyOn(console, 'log').mockImplementation(() => {});
  verifyLocaleParity(ctx);
  return { ctx, errors: error.mock.calls.map(String), logs: log.mock.calls.map(String) };
}

const en = { greeting: 'Hello {name}', save: 'Save the file' };
const passLine = (lang: string) =>
  `  ✅ ${lang}.json 全量 parity / 占位符 / 壳 / 双语对照 / 纯净门禁 检测 通过`;

describe('verifyLocaleParity', () => {
  it('prints the pass line for a locale that matches en', () => {
    const { ctx, errors, logs } = runParity({ en, zh: { greeting: '你好 {name}', save: '保存文件' } });
    expect(errors).toEqual([]);
    expect(ctx.hasErrors).toBe(false);
    expect(logs).toContain(passLine('zh'));
  });

  it('fails on an orphan key and does not print the pass line for that locale', () => {
    const { ctx, errors, logs } = runParity({
      en,
      zh: { greeting: '你好 {name}', save: '保存文件', stale: '已过期' },
    });
    expect(ctx.hasErrors).toBe(true);
    expect(errors.some((line) => line.includes('zh.json 存在 1 个 en 中没有的键（孤儿键，须清理）'))).toBe(true);
    expect(logs).not.toContain(passLine('zh'));
  });

  it('treats a zh-only key under settings.plugins.import.capabilities as an orphan', () => {
    const { ctx, errors } = runParity({
      en,
      zh: {
        greeting: '你好 {name}',
        save: '保存文件',
        settings: { plugins: { import: { capabilities: { extra: '额外' } } } },
      },
    });
    expect(ctx.hasErrors).toBe(true);
    expect(errors.some((line) => line.includes('zh.json 存在 1 个 en 中没有的键（孤儿键，须清理）'))).toBe(true);
  });

  it('reports missing keys and placeholder drift', () => {
    const { ctx, errors } = runParity({ en, zh: { greeting: '你好 {user}' } });
    expect(ctx.hasErrors).toBe(true);
    expect(errors.some((line) => line.includes('zh.json 缺少 1 个 en 键'))).toBe(true);
    expect(errors.some((line) => line.includes('zh.json 存在 1 个占位符不匹配'))).toBe(true);
  });

  it('flags a whole-sentence English leftover in zh', () => {
    const { errors } = runParity({
      en,
      zh: { greeting: '你好 {name}', save: 'Please save the file now.' },
    });
    expect(errors.some((line) => line.includes('zh.json 存在 1 个句子级纯英文残留键'))).toBe(true);
  });

  it('flags a polluted en source with CJK text', () => {
    const { ctx, errors } = runParity({ en: { greeting: 'Hello 你好' }, zh: { greeting: '你好' } });
    expect(ctx.hasErrors).toBe(true);
    expect(errors.some((line) => line.includes('en.json 存在 1 个混入非拉丁文字的键'))).toBe(true);
  });
});
