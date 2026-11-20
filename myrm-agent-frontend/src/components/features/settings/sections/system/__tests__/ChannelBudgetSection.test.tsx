import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChannelBudgetSection from '../ChannelBudgetSection';
import {
  getChannelAudit,
  getChannelBudgets,
  type ChannelAuditEntry,
  type ChannelBudgetStatus,
} from '@/services/budget';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/budget', () => ({
  getChannelBudgets: vi.fn(),
  updateChannelBudget: vi.fn(),
  deleteChannelBudget: vi.fn(),
  getChannelAudit: vi.fn(),
}));

const CHANNEL_KEY = 'telegram:group:g-1';

const channelStatus = (todayCostUsd: number): ChannelBudgetStatus => ({
  channel_key: CHANNEL_KEY,
  label: '',
  enabled: true,
  daily_limit_usd: 2,
  today_cost_usd: todayCostUsd,
  remaining_usd: Math.max(2 - todayCostUsd, 0),
  usage_pct: (todayCostUsd / 2) * 100,
  status: 'ok',
});

const auditEntry = (senderId: string, totalCostUsd: number): ChannelAuditEntry => ({
  sender_id: senderId,
  message_count: 3,
  total_cost_usd: totalCostUsd,
});

async function openAudit(todayCostUsd: number, entries: ChannelAuditEntry[]) {
  vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [], statuses: [channelStatus(todayCostUsd)] });
  vi.mocked(getChannelAudit).mockResolvedValue({
    channel_key: CHANNEL_KEY,
    period_days: 7,
    entries,
    total_cost_usd: entries.reduce((sum, entry) => sum + entry.total_cost_usd, 0),
  });

  render(<ChannelBudgetSection />);
  fireEvent.click(await screen.findByText('auditDetails'));
  await screen.findByText(entries[0].sender_id);
}

/** Width of the share bar drawn in the audit row of `senderId`. */
const shareBarWidth = (senderId: string): string => {
  const row = screen.getByText(senderId).closest('div');
  return row?.querySelector<HTMLElement>('[style]')?.style.width ?? '';
};

describe('ChannelBudgetSection audit', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // The window covers several days, so a sender's share is taken of what the window cost, not of what today cost.
  it.each([0, 0.5, 10])(
    'sizes the sender bars by their share of the window when today cost %s',
    async (todayCostUsd) => {
      await openAudit(todayCostUsd, [auditEntry('alice', 3), auditEntry('bob', 1)]);

      expect(shareBarWidth('alice')).toBe('75%');
      expect(shareBarWidth('bob')).toBe('25%');
    },
  );

  it('keeps the bars empty when the window cost nothing', async () => {
    await openAudit(0, [auditEntry('alice', 0)]);

    expect(shareBarWidth('alice')).toBe('0%');
  });
});
