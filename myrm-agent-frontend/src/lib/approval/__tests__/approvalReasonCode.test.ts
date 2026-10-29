import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { APPROVAL_REASON_CODES, parseApprovalReasonCode } from '@/lib/approval/approvalReasonCode';

const LOCALES = ['en', 'zh', 'zh-TW', 'ja', 'ko', 'de'] as const;
/** A code that names no path, file or domain has no subject to show. */
const CODES_WITHOUT_SUBJECT = new Set(['shell_threat']);

function reasonCopy(locale: string): Record<string, unknown> {
  const messages = JSON.parse(readFileSync(path.join(process.cwd(), 'locales', `${locale}.json`), 'utf8')) as {
    toolApproval: { reasons?: Record<string, unknown> };
  };
  return messages.toolApproval.reasons ?? {};
}

describe('parseApprovalReasonCode', () => {
  it('accepts exactly the codes the card has copy for', () => {
    for (const code of APPROVAL_REASON_CODES) {
      expect(parseApprovalReasonCode(code)).toBe(code);
    }
  });

  it('drops a code it has no copy for, so the card shows the reason as written', () => {
    expect(parseApprovalReasonCode('a_future_code')).toBeUndefined();
    expect(parseApprovalReasonCode('')).toBeUndefined();
    expect(parseApprovalReasonCode(undefined)).toBeUndefined();
    expect(parseApprovalReasonCode(7)).toBeUndefined();
  });
});

describe.each(LOCALES)('approval reason copy in %s', (locale) => {
  it('words every code, and no other', () => {
    expect(Object.keys(reasonCopy(locale)).sort()).toEqual([...APPROVAL_REASON_CODES].sort());
  });

  it.each(APPROVAL_REASON_CODES)('shows the subject inside the sentence for %s', (code) => {
    const text = reasonCopy(locale)[code];

    expect(typeof text).toBe('string');
    expect((text as string).trim()).not.toBe('');
    expect((text as string).includes('{subject}')).toBe(!CODES_WITHOUT_SUBJECT.has(code));
  });
});
