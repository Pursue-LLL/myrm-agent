import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { WeekDistributionChart } from '../UsageDistributionCharts';
import { getUserTimezone } from '@/services/statistics';

describe('UsageDistributionCharts & Timezone Suite', () => {
  it('getUserTimezone returns a non-empty string fallback to UTC if needed', () => {
    const tz = getUserTimezone();
    expect(typeof tz).toBe('string');
    expect(tz.length).toBeGreaterThan(0);
  });

  it('renders English weekday labels when locale is en', () => {
    const data = { '0': 5, '1': 10, '2': 0, '3': 2, '4': 8, '5': 1, '6': 0 };
    render(<WeekDistributionChart data={data} locale="en" />);

    expect(screen.getByText('Mon')).toBeInTheDocument();
    expect(screen.getByText('Wed')).toBeInTheDocument();
    expect(screen.getByText('Sun')).toBeInTheDocument();
  });

  it('renders Chinese bilingual weekday labels when locale is zh', () => {
    const data = { '0': 5, '1': 10, '2': 0, '3': 2, '4': 8, '5': 1, '6': 0 };
    render(<WeekDistributionChart data={data} locale="zh" />);

    expect(screen.getByText('周一')).toBeInTheDocument();
    expect(screen.getByText('周三')).toBeInTheDocument();
    expect(screen.getByText('周日')).toBeInTheDocument();
  });
});
