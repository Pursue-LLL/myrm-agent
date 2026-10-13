/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SkillTrendChart from '../SkillTrendChart';
import type { SkillTrendSeries } from '@/services/statistics';

const TRUNCATED_NOTE = 'Earlier runs in this range are not shown.';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => (key === 'skillTrends.truncated' ? TRUNCATED_NOTE : key),
}));

const series = (skill_name: string, truncated: boolean): SkillTrendSeries => ({
  skill_name,
  truncated,
  data_points: [{ date: '2026-10-12', success_rate: 1, observed_count: 3, call_count: 3 }],
});

describe('SkillTrendChart', () => {
  it('says so when the selected skill ran more often than its history keeps', () => {
    render(<SkillTrendChart trends={[series('hourly-job', true), series('occasional', false)]} />);

    expect(screen.getByText(TRUNCATED_NOTE)).toBeInTheDocument();
  });

  it('stays quiet for a skill whose history covers the range, and follows the selected skill', () => {
    render(<SkillTrendChart trends={[series('hourly-job', true), series('occasional', false)]} />);

    fireEvent.click(screen.getByRole('button', { name: 'occasional' }));

    expect(screen.queryByText(TRUNCATED_NOTE)).not.toBeInTheDocument();
  });
});
