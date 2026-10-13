/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SkillTrendChart from '../SkillTrendChart';
import type { SkillTrendSeries } from '@/services/statistics';

const TRUNCATED_NOTE = 'Earlier runs in this range are not shown.';

const stableT = (key: string) => (key === 'skillTrends.truncated' ? TRUNCATED_NOTE : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const series = (skill_name: string, truncated: boolean): SkillTrendSeries => ({
  skill_name,
  truncated,
  data_points: [{ date: '2026-10-12', success_rate: 1, observed_count: 3, call_count: 3 }],
});

describe('SkillTrendChart', () => {
  it('notes that earlier runs may be missing when the skill outgrew the history kept for it', () => {
    render(<SkillTrendChart trends={[series('hourly-job', true), series('occasional', false)]} />);

    expect(screen.getByText(TRUNCATED_NOTE)).toBeInTheDocument();
  });

  it('stays quiet for a skill whose history covers the range, and follows the selected skill', () => {
    render(<SkillTrendChart trends={[series('hourly-job', true), series('occasional', false)]} />);

    fireEvent.click(screen.getByRole('button', { name: 'occasional' }));

    expect(screen.queryByText(TRUNCATED_NOTE)).not.toBeInTheDocument();
  });

  it('says that nothing ran in the range instead of drawing an empty chart', () => {
    render(<SkillTrendChart trends={[]} />);

    expect(screen.getByText('skillTrends.empty')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('lights the busiest skill when a new range no longer contains the selected one', () => {
    const { rerender } = render(
      <SkillTrendChart trends={[series('hourly-job', false), series('occasional', false)]} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'occasional' }));
    expect(screen.getByRole('button', { name: 'occasional' })).toHaveAttribute('aria-pressed', 'true');

    rerender(<SkillTrendChart trends={[series('hourly-job', false)]} />);

    expect(screen.getByRole('button', { name: 'hourly-job' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('keeps the chart on a skill that has a pill when the selection falls outside the shown ones', () => {
    const tenSkills = (prefix: string) => Array.from({ length: 10 }, (_, index) => `${prefix}-${index}`);
    const seriesOf = (names: string[]) => names.map((name) => series(name, false));
    const { rerender } = render(<SkillTrendChart trends={seriesOf(tenSkills('old'))} />);
    fireEvent.click(screen.getByRole('button', { name: 'old-9' }));

    rerender(<SkillTrendChart trends={seriesOf([...tenSkills('new'), 'old-9'])} />);

    expect(screen.getAllByRole('button', { pressed: true })).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'new-0' })).toHaveAttribute('aria-pressed', 'true');
  });
});
