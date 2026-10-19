/**
 * [INPUT]
 * - myrm-agent-server/app/schemas/memory/import_warning_codes.py (POS: 记忆导入告警码 SSOT)
 * - locales/{en,zh,zh-TW,ja,ko,de}.json (POS: 六语言文案 SSOT)
 *
 * [OUTPUT]
 * 告警码 ↔ 六语言文案契约测试。
 *
 * [POS]
 * 记忆导入告警码的跨仓契约：服务端声明的每个告警码都必须在六语言 memory.importWarnings
 * 命名空间里有文案，且文案里不得出现未声明的多余键——新增告警码时这里先失败，
 * 避免六语言产品里冒出英文裸码。
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

// Vitest runs with the frontend package as the working directory.
const REPO_ROOT = path.resolve(process.cwd(), '..');
const VOCABULARY_PATH = path.join(REPO_ROOT, 'myrm-agent-server/app/schemas/memory/import_warning_codes.py');
const LOCALES = ['en', 'zh', 'zh-TW', 'ja', 'ko', 'de'] as const;

const readDeclaredCodes = (): string[] => {
  const source = readFileSync(VOCABULARY_PATH, 'utf8');
  const start = source.indexOf('ImportWarningCode = Literal[');
  const end = source.indexOf(']', start);
  if (start === -1 || end === -1) {
    throw new Error('ImportWarningCode literal block not found');
  }
  return [...source.slice(start, end).matchAll(/"([a-z0-9_]+)"/g)].map((match) => match[1]);
};

const readWarnings = (locale: string): Record<string, string> => {
  const raw = readFileSync(path.join(process.cwd(), 'locales', `${locale}.json`), 'utf8');
  const messages = JSON.parse(raw) as { memory: { importWarnings: Record<string, string> } };
  return messages.memory.importWarnings;
};

describe('memory import warning copy contract', () => {
  const declared = readDeclaredCodes();

  it('declares the vocabulary the server scans for', () => {
    expect(declared.length).toBeGreaterThan(20);
    expect(new Set(declared).size).toBe(declared.length);
  });

  it.each(LOCALES)('translates every declared code into %s', (locale) => {
    const warnings = readWarnings(locale);
    const missing = declared.filter((code) => !warnings[code]?.trim());

    expect(missing).toEqual([]);
  });

  it.each(LOCALES)('has no %s copy outside the declared vocabulary', (locale) => {
    const warnings = readWarnings(locale);
    const extra = Object.keys(warnings).filter((key) => !declared.includes(key));

    expect(extra).toEqual([]);
  });
});
