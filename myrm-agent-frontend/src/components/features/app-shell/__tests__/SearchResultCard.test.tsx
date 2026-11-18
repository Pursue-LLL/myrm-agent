/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SearchResultCard } from '@/components/features/app-shell/SearchResultCard';
import type { MockLocale } from '@/test-utils/realIntl';
import type { SearchResult } from '@/services/chatHistorySearch';

const intl = vi.hoisted(() => ({ locale: 'en' as MockLocale }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

const hit = (role: string): SearchResult => ({
  id: 'm1',
  chat_id: 'c1',
  chat_title: 'Quarterly plan',
  role,
  content: 'the full message',
  snippet: 'the <mark>matched</mark> part',
  sent_at: '2026-08-04T10:00:00.000Z',
});

function renderCard(role: string) {
  return render(<SearchResultCard item={hit(role)} onOpen={vi.fn()} onCite={vi.fn()} />);
}

describe('SearchResultCard speaker label', () => {
  afterEach(() => {
    intl.locale = 'en';
  });

  it.each([
    ['en', 'user', 'You'],
    ['en', 'assistant', 'Assistant'],
    ['zh', 'user', '你'],
    ['zh', 'assistant', '助手'],
  ] as const)('in %s a %s message is labelled %s', (locale, role, label) => {
    intl.locale = locale;

    renderCard(role);

    expect(screen.getByText(label)).toBeTruthy();
    expect(screen.queryByText(role)).toBeNull();
  });
});
