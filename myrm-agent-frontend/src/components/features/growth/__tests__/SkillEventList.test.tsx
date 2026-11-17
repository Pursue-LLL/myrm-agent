/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SkillEventList from '../SkillEventList';
import type { SkillEvolutionEvent } from '@/services/statistics';

const stableT = Object.assign((key: string) => key, { has: () => true });

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const NOW = new Date('2026-01-10T12:00:00Z');

function eventCreatedAt(createdAt: string): SkillEvolutionEvent {
  return {
    skill_id: 'skill-1',
    skill_name: 'super_search',
    source: 'draft',
    status: 'PENDING_REVIEW',
    growth_type: 'skill_draft',
    created_at: createdAt,
    change_summary: 'Tighten the query rewrite step',
  };
}

describe('SkillEventList', () => {
  const originalTimeZone = process.env.TZ;

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
    // A device far ahead of UTC pushes a timestamp read as local time onto the wrong day.
    process.env.TZ = 'Pacific/Auckland';
  });

  afterEach(() => {
    vi.useRealTimers();
    if (originalTimeZone === undefined) {
      delete process.env.TZ;
    } else {
      process.env.TZ = originalTimeZone;
    }
  });

  it.each([
    ['carries no offset (what the server sends)', '2026-01-09T20:00:00'],
    ['ends in Z', '2026-01-09T20:00:00Z'],
    ['names a UTC offset', '2026-01-09T20:00:00+00:00'],
  ])('dates an event whose timestamp %s by when it happened in UTC', (_case, createdAt) => {
    render(<SkillEventList events={[eventCreatedAt(createdAt)]} />);

    expect(screen.getByText('16 hours ago')).toBeInTheDocument();
  });

  it('says nothing about time for an event whose timestamp cannot be read', () => {
    render(<SkillEventList events={[eventCreatedAt('not-a-date')]} />);

    expect(screen.getByText('super_search')).toBeInTheDocument();
    expect(screen.queryByText(/ago|invalid/i)).not.toBeInTheDocument();
  });
});
