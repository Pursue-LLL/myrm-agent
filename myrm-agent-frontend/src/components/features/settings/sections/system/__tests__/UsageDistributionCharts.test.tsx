/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const stableT = (key: string, values?: Record<string, unknown>) =>
  values ? `${key}:${Object.values(values).join('/')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

import { ActivityDailyChart } from '../UsageDistributionCharts';

describe('ActivityDailyChart bar tooltips', () => {
  it('renders one translated tooltip per day with the date and call count', () => {
    render(
      <ActivityDailyChart
        data={[
          { date: '2026-11-01', tool_calls: 12 },
          { date: '2026-11-02', tool_calls: 0 },
        ]}
      />,
    );

    expect(screen.getByTitle('dailyToolCallsTooltip:2026-11-01/12')).toBeInTheDocument();
    expect(screen.getByTitle('dailyToolCallsTooltip:2026-11-02/0')).toBeInTheDocument();
  });

  it('renders nothing when there is no activity', () => {
    const { container } = render(<ActivityDailyChart data={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
