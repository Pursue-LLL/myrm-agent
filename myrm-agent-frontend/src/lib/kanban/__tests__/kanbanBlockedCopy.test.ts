import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { AbstractIntlMessages } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';
import blockedReasons from '@shared/config/kanban_blocked_reasons.json';
import type { BlockKind } from '@/services/kanban';

// The global test setup replaces next-intl with an identity translator, which cannot tell a missing message from a present one.
const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');

const LOCALES = ['en', 'zh', 'zh-TW', 'ja', 'ko', 'de'] as const;

// Typed as a record so that adding a kind to `BlockKind` fails compilation here until its copy is covered below.
const BLOCK_KINDS: Record<BlockKind, true> = { human: true, scheduled: true, external: true };

function kanbanTranslator(locale: string) {
  const errors: string[] = [];
  const messages = JSON.parse(
    readFileSync(join(process.cwd(), 'locales', `${locale}.json`), 'utf-8'),
  ) as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: 'kanban', onError: (error) => errors.push(error.message) });
  return { t: t as (key: string) => string, errors };
}

describe.each(LOCALES)('kanban blocked-state copy in %s', (locale) => {
  it('has a sentence for every reason in the shared table', () => {
    const { t, errors } = kanbanTranslator(locale);

    for (const id of Object.keys(blockedReasons)) {
      expect(t(`blockedReason.${id}`), `blockedReason.${id}`).not.toMatch(/^(kanban\.)?blockedReason\./);
    }
    expect(errors).toEqual([]);
  });

  it('names every kind of block and the countdown shown once a scheduled time has passed', () => {
    const { t, errors } = kanbanTranslator(locale);

    for (const kind of Object.keys(BLOCK_KINDS)) {
      expect(t(`blockKind.${kind}`), `blockKind.${kind}`).not.toMatch(/^(kanban\.)?blockKind\./);
    }
    expect(t('autoUnblocking')).not.toMatch(/^(kanban\.)?autoUnblocking$/);
    expect(errors).toEqual([]);
  });
});
