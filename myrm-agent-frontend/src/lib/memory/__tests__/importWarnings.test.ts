/**
 * [INPUT]
 * ../importWarnings::resolveImportWarning (POS: 记忆导入告警文案解析)
 *
 * [OUTPUT]
 * importWarnings 单测：已知告警码走文案、未知码不泄漏裸标识符。
 *
 * [POS]
 * 记忆导入告警文案解析回归测试。
 */
import { describe, expect, it } from 'vitest';

import { resolveImportWarning, type ImportWarningTranslator } from '../importWarnings';

const translator = (messages: Record<string, string>): ImportWarningTranslator =>
  Object.assign((key: string) => messages[key] ?? key, {
    has: (key: string) => key in messages,
  });

describe('resolveImportWarning', () => {
  it('uses the shared warning copy for known codes', () => {
    const t = translator({ pasted_empty: 'Nothing could be parsed.' });

    expect(resolveImportWarning('pasted_empty', t)).toBe('Nothing could be parsed.');
  });

  it('humanizes unknown codes instead of leaking the raw identifier', () => {
    const t = translator({});

    expect(resolveImportWarning('brand_new_warning_code', t)).toBe('Brand new warning code');
  });

  it('passes through free-text warnings untouched', () => {
    const t = translator({});
    const sentence = 'Repeated entries in the pasted text are imported once.';

    expect(resolveImportWarning(sentence, t)).toBe(sentence);
  });
});
