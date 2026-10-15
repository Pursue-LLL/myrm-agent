import { describe, expect, it } from 'vitest';
import blockedReasons from '@shared/config/kanban_blocked_reasons.json';
import { blockedReasonText } from '../kanbanBlockedReason';

const translate = (key: string): string => `translated:${key}`;

describe('blockedReasonText', () => {
  it('shows the interface-language text for a dependency whose merge failed', () => {
    expect(blockedReasonText(blockedReasons.parentMergeFailed, translate)).toBe(
      'translated:blockedReason.parentMergeFailed',
    );
  });

  it('returns a reason it does not know exactly as written', () => {
    expect(blockedReasonText('Waiting for the model usage limit to reset; resumes automatically', translate)).toBe(
      'Waiting for the model usage limit to reset; resumes automatically',
    );
  });

  it('does not treat an inherited object key as a known reason', () => {
    expect(blockedReasonText('constructor', translate)).toBe('constructor');
  });
});
