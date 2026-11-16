// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createContext } from '../verify-i18n/context.mjs';
import { verifyKanbanClosure } from '../verify-i18n/namespace-keys.mjs';
import { verifyEnglishSentenceResidue } from '../verify-i18n/purity-gates.mjs';
import {
  NON_LATIN_RE,
  containsResidue,
  isBilingualDirty,
  isEnglishSentenceResidue,
  placeholderSet,
} from '../verify-i18n/value-rules.mjs';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('placeholderSet', () => {
  it('is order-insensitive and keeps only argument names', () => {
    expect(placeholderSet('{b} and {a}')).toBe('a|b');
    expect(placeholderSet('{count, plural, one {# item} other {# items}}')).toBe('count');
    expect(placeholderSet('No placeholders')).toBe('');
  });
});

describe('isBilingualDirty', () => {
  it('flags "local / English" pairs in either order', () => {
    expect(isBilingualDirty('是 / Yes')).toBe(true);
    expect(isBilingualDirty('Context Health / 上下文健康')).toBe(true);
  });

  it('flags legitimate term pairs too; they must be exempted through the allowlist', () => {
    expect(isBilingualDirty('MCP / 技能设置')).toBe(true);
  });

  it('ignores placeholder pairs, single-language values and over-long values', () => {
    expect(isBilingualDirty('{shown} / {total}')).toBe(false);
    expect(isBilingualDirty('是')).toBe(false);
    expect(isBilingualDirty('Yes / No')).toBe(false);
    expect(isBilingualDirty(`是 / ${'Y'.repeat(200)}`)).toBe(false);
    expect(isBilingualDirty(['是 / Yes'] as unknown as string)).toBe(false);
  });
});

describe('containsResidue', () => {
  it('tests strings directly and arrays element by element', () => {
    expect(containsResidue('File 漢字', NON_LATIN_RE)).toBe(true);
    expect(containsResidue(['File', '漢字'], NON_LATIN_RE)).toBe(true);
    expect(containsResidue(['File', 42], NON_LATIN_RE)).toBe(false);
    expect(containsResidue(42, NON_LATIN_RE)).toBe(false);
  });

  it('covers Han, kana, hangul and full-width punctuation, but not Latin text', () => {
    for (const sample of ['汉', 'あ', '한', '，']) {
      expect(NON_LATIN_RE.test(sample), sample).toBe(true);
    }
    expect(NON_LATIN_RE.test('Save the file, please.')).toBe(false);
  });
});

describe('isEnglishSentenceResidue', () => {
  it('flags whole-sentence English', () => {
    expect(isEnglishSentenceResidue('Please click the button to continue.')).toBe(true);
    expect(isEnglishSentenceResidue('Save changes')).toBe(true);
  });

  it('keeps credential names, brand names and single words (even with sentence cues)', () => {
    for (const value of ['App ID', 'Bot Token', 'Client Secret', 'Alibaba Cloud', 'Token', 'Cancel', 'Done.']) {
      expect(isEnglishSentenceResidue(value)).toBe(false);
    }
  });
});

describe('verifyEnglishSentenceResidue', () => {
  const config = { shellAllowlists: { allowedSameValues: new Set<string>(), allowedSameKeys: new Set<string>() } };

  function run(localeValue: string, lang = 'zh') {
    const ctx = createContext('/unused');
    ctx.translations = { en: { k: 'Please click the button to continue.' }, [lang]: { k: localeValue } };
    vi.spyOn(console, 'error').mockImplementation(() => {});
    return { ctx, errors: verifyEnglishSentenceResidue(ctx, config, lang, ['k']) };
  }

  it('flags an untranslated sentence even when it carries non-ASCII punctuation', () => {
    expect(run('Please click the button… to proceed.').errors).toEqual(['k']);
    expect(run('Please click the button — to proceed').errors).toEqual(['k']);
    expect(run('Please click the button to proceed.').ctx.hasErrors).toBe(true);
  });

  it('accepts values that contain a non-ASCII letter', () => {
    const { ctx, errors } = run('点击按钮继续 — please wait');
    expect(errors).toEqual([]);
    expect(ctx.hasErrors).toBe(false);
  });

  it('judges zh only', () => {
    const { ctx, errors } = run('Please click the button to proceed.', 'en');
    expect(errors).toEqual([]);
    expect(ctx.hasErrors).toBe(false);
  });
});

const KANBAN_KEYS = [
  'executionTrace',
  'openSourceChat',
  'viewBoardTasksFromChat',
  'sourceChatFilterActive',
  'chatTaskCreatedTitle',
  'chatTaskCreatedSuccess',
  'chatTaskCreatedOpenBoard',
  'clearSourceChatFilter',
];
const completeKanban = () => Object.fromEntries(KANBAN_KEYS.map((key) => [key, `text:${key}`]));

function runKanbanCheck(translations: Record<string, unknown>) {
  const ctx = createContext('/unused');
  ctx.translations = translations;
  const error = vi.spyOn(console, 'error').mockImplementation(() => {});
  const log = vi.spyOn(console, 'log').mockImplementation(() => {});
  verifyKanbanClosure(ctx);
  return { ctx, errors: error.mock.calls.map(String), logs: log.mock.calls.map(String) };
}

describe('required-key checks (shared helper behind configPanel / kanban / artifacts)', () => {
  it('passes loaded languages that carry every required key and skips languages that failed to load', () => {
    const { ctx, errors, logs } = runKanbanCheck({ en: { kanban: completeKanban() } });
    expect(ctx.hasErrors).toBe(false);
    expect(errors).toEqual([]);
    expect(logs.some((line) => line.includes('en.json kanban Chat↔Board closure keys 完整'))).toBe(true);
    expect(logs.some((line) => line.includes('zh.json'))).toBe(false);
  });

  it('reports missing and empty keys, and a missing section', () => {
    const { ctx, errors } = runKanbanCheck({
      en: { kanban: { ...completeKanban(), executionTrace: '', openSourceChat: undefined } },
      zh: {},
    });
    expect(ctx.hasErrors).toBe(true);
    expect(errors).toContain('  ❌ en.json kanban 缺少或非空字符串: executionTrace, openSourceChat');
    expect(errors).toContain('  ❌ zh.json 缺少或无效 kanban');
  });
});
