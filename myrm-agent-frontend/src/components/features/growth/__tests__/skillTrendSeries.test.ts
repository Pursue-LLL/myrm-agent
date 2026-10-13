import { describe, expect, it } from 'vitest';
import type { SkillTrendPoint } from '@/services/statistics';
import { fillIdleDays, formatBarValue, toBarData } from '../skillTrendSeries';

const point = (
  date: string,
  success_rate: number | null,
  observed_count: number,
  call_count: number,
): SkillTrendPoint => ({
  date,
  success_rate,
  observed_count,
  call_count,
});

describe('fillIdleDays', () => {
  it('inserts the days without runs between the first and the last run', () => {
    const first = point('2026-10-01', 1, 2, 2);
    const last = point('2026-10-05', 0, 1, 1);

    const filled = fillIdleDays([first, last]);

    expect(filled.map((p) => p.date)).toEqual(['2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04', '2026-10-05']);
    expect(filled[0]).toBe(first);
    expect(filled[4]).toBe(last);
    expect(filled[2]).toEqual({ date: '2026-10-03', success_rate: null, observed_count: 0, call_count: 0 });
  });

  it('keeps calendar days across month and year ends and leap days', () => {
    const dates = (from: string, to: string) =>
      fillIdleDays([point(from, 1, 1, 1), point(to, 1, 1, 1)]).map((p) => p.date);

    expect(dates('2026-02-27', '2026-03-02')).toEqual(['2026-02-27', '2026-02-28', '2026-03-01', '2026-03-02']);
    expect(dates('2028-02-28', '2028-03-01')).toEqual(['2028-02-28', '2028-02-29', '2028-03-01']);
    expect(dates('2026-12-31', '2027-01-01')).toEqual(['2026-12-31', '2027-01-01']);
  });

  it('does not depend on the order the days arrive in', () => {
    const filled = fillIdleDays([point('2026-10-03', 1, 1, 1), point('2026-10-01', 1, 1, 1)]);

    expect(filled.map((p) => p.date)).toEqual(['2026-10-01', '2026-10-02', '2026-10-03']);
  });

  it('leaves a single day, and days it cannot read, as they are', () => {
    const single = [point('2026-10-01', 1, 1, 1)];
    const unreadable = [point('2026-10-01', 1, 1, 1), point('not-a-date', 1, 1, 1)];

    expect(fillIdleDays(single)).toBe(single);
    expect(fillIdleDays(unreadable)).toBe(unreadable);
  });
});

describe('toBarData', () => {
  const points = [point('2026-10-01', 1, 2, 2), point('2026-10-03', 0, 1, 1), point('2026-10-04', null, 0, 3)];

  it('tells a day that failed (0) from a day nothing was observed on (null) in the success rate', () => {
    expect(toBarData(points, 'success_rate').map((d) => d.value)).toEqual([1, null, 0, null]);
  });

  it('leaves the days without runs empty in the run count', () => {
    expect(toBarData(points, 'call_count').map((d) => d.value)).toEqual([2, null, 1, 3]);
  });

  it('carries the evidence the tooltip needs', () => {
    expect(toBarData(points, 'success_rate')[2]).toEqual({
      date: '2026-10-03',
      value: 0,
      observedCount: 1,
      callCount: 1,
    });
  });
});

describe('formatBarValue', () => {
  const datum = (value: number | null, callCount = 0) => ({ date: '2026-10-01', value, observedCount: 0, callCount });

  it('writes the success rate as a percentage and an unobserved day as a dash', () => {
    expect(formatBarValue('success_rate', datum(0.625))).toBe('63%');
    expect(formatBarValue('success_rate', datum(0))).toBe('0%');
    expect(formatBarValue('success_rate', datum(null))).toBe('–');
  });

  it('writes the run count of the day, including none', () => {
    expect(formatBarValue('call_count', datum(null, 0))).toBe('0');
    expect(formatBarValue('call_count', datum(7, 7))).toBe('7');
  });
});
