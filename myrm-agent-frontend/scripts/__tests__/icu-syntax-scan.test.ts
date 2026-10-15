// @vitest-environment node
import { createTranslator, IntlErrorCode } from 'use-intl/core';
import { describe, expect, it } from 'vitest';

import { scanIcuMessages } from '../icu-syntax-scan';

const invalid = (tree: unknown) => scanIcuMessages(tree).invalid;

describe('scanIcuMessages: valid messages', () => {
  it('accepts plain text, named arguments, plurals and rich-text tags', () => {
    const tree = {
      plain: 'Save changes',
      named: '{count} memories need migration',
      plural: '{count, plural, one {# item} other {# items}}',
      rich: 'Read the <link>docs</link>',
      cjk: '用法：/goal <目标> | status',
    };
    expect(invalid(tree)).toEqual([]);
  });

  it('accepts literal braces and angle brackets that are wrapped in apostrophes', () => {
    const tree = {
      secret: "Use '{{secret:KEY}}' to reference secrets",
      token: "Bearer '<token>'",
      json: `Format: [ '{"question": "...", "answer": "..."}' ]`,
    };
    expect(invalid(tree)).toEqual([]);
  });
});

describe('scanIcuMessages: invalid messages', () => {
  it('rejects double-brace placeholders, bare angle brackets and bare JSON braces', () => {
    const tree = {
      count: '{{count}} memories need migration',
      token: 'Bearer <token>',
      json: 'Format: [{"question": "..."}]',
    };
    expect(invalid(tree)).toEqual([
      { path: 'count', error: 'MALFORMED_ARGUMENT' },
      { path: 'token', error: 'UNCLOSED_TAG' },
      { path: 'json', error: 'MALFORMED_ARGUMENT' },
    ]);
  });

  it('reports nested paths and array element indexes', () => {
    const tree = { settings: { hint: 'Use {{x}}', list: ['fine', 'Use <b'] } };
    expect(invalid(tree).map((message) => message.path)).toEqual(['settings.hint', 'settings.list.1']);
  });

  it('counts every string leaf and ignores non-string values', () => {
    const tree = { a: 'one', b: { c: 'two', d: 3, e: null, f: true }, g: ['three'] };
    expect(scanIcuMessages(tree)).toEqual({ scanned: 3, invalid: [] });
  });
});

describe('scanIcuMessages: agreement with the runtime message compiler', () => {
  // `{}` values force the compile path in every use-intl build, so this is the syntax oracle for a message.
  // Only INVALID_MESSAGE counts: missing argument values are formatting errors, not syntax errors.
  const compiles = (message: string): boolean => {
    let failed = false;
    const t = createTranslator({
      locale: 'en',
      messages: { m: message },
      onError: (error) => {
        failed = failed || error.code === IntlErrorCode.INVALID_MESSAGE;
      },
    });
    t('m', {});
    return !failed;
  };

  const samples = [
    '{count} memories',
    '{{count}} memories',
    'Bearer <token>',
    "Bearer '<token>'",
    "Use '{{secret:KEY}}' here",
    'Use {{secret:KEY}} here',
    '{items, plural, one {# row} other {# rows}}',
    'Format: [{"a": 1}]',
    `Format: [ '{"a": 1}' ]`,
    `Format: '[{"a": 1}]'`,
    'Do not use <b>',
  ];

  it.each(samples)('%s', (message) => {
    expect(invalid({ m: message }).length === 0).toBe(compiles(message));
  });
});
