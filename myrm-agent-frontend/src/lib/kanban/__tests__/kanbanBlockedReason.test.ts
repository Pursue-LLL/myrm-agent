import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import blockedReasons from '@shared/config/kanban_blocked_reasons.json';
import { blockedReasonText } from '../kanbanBlockedReason';

const translate = (key: string): string => `translated:${key}`;
const LOCALES = ['en', 'zh', 'zh-TW', 'ja', 'ko', 'de'];

interface KanbanMessages {
  kanban: { blockedReason: Record<string, string> };
}

describe('blockedReasonText', () => {
  it('shows the interface-language text for a dependency whose merge failed', () => {
    expect(blockedReasonText(blockedReasons.parentMergeFailed, translate)).toBe(
      'translated:blockedReason.parentMergeFailed',
    );
  });

  it('shows the interface-language text for a task waiting on the usage limit and for a batch pause', () => {
    expect(blockedReasonText(blockedReasons.usageLimit, translate)).toBe('translated:blockedReason.usageLimit');
    expect(blockedReasonText(blockedReasons.batchPause, translate)).toBe('translated:blockedReason.batchPause');
  });

  it('returns a reason it does not know exactly as written', () => {
    expect(blockedReasonText('Budget exhausted after 12 turns', translate)).toBe('Budget exhausted after 12 turns');
  });

  it('does not treat an inherited object key as a known reason', () => {
    expect(blockedReasonText('constructor', translate)).toBe('constructor');
  });

  it.each(LOCALES)('has a text for every reason in the shared file in the %s locale', (locale) => {
    const messages = JSON.parse(
      readFileSync(join(process.cwd(), 'locales', `${locale}.json`), 'utf-8'),
    ) as KanbanMessages;

    for (const id of Object.keys(blockedReasons)) {
      expect(messages.kanban.blockedReason[id], `${locale}: kanban.blockedReason.${id}`).toBeTruthy();
    }
  });
});
