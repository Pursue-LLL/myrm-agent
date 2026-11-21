import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChannelBudgetSection from '../ChannelBudgetSection';
import {
  createChannelBudget,
  getChannelAudit,
  getChannelBudgets,
  updateChannelBudget,
  type ChannelAuditEntry,
  type ChannelBudgetPolicy,
  type ChannelBudgetsResponse,
  type ChannelBudgetStatus,
} from '@/services/budget';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/budget', () => ({
  getChannelBudgets: vi.fn(),
  createChannelBudget: vi.fn(),
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

const policyOf = (dailyLimitUsd: number): ChannelBudgetPolicy => ({
  channel_key: CHANNEL_KEY,
  daily_limit_usd: dailyLimitUsd,
  warning_threshold: 0.8,
  enabled: true,
  label: '',
});

/** A promise the test settles by hand, to hold a request in flight. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

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

describe('ChannelBudgetSection saving', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // The limit field saves on blur and the switch on click, each from the policy last loaded. A save that carried the
  // whole policy would send the old limit back from a switch click that lands while the limit is still being saved.
  it('sends each edit as a patch of its own field, even while an earlier save is in flight', async () => {
    const limitSave = deferred<ChannelBudgetPolicy>();
    vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [policyOf(2)], statuses: [channelStatus(0)] });
    vi.mocked(updateChannelBudget).mockReturnValueOnce(limitSave.promise).mockResolvedValue(policyOf(5));

    render(<ChannelBudgetSection />);
    const limitInput = await screen.findByDisplayValue('2');
    fireEvent.change(limitInput, { target: { value: '5' } });
    fireEvent.blur(limitInput);
    fireEvent.click(screen.getByRole('switch'));

    expect(updateChannelBudget).toHaveBeenCalledTimes(2);
    expect(updateChannelBudget).toHaveBeenNthCalledWith(1, CHANNEL_KEY, { daily_limit_usd: 5 });
    expect(updateChannelBudget).toHaveBeenNthCalledWith(2, CHANNEL_KEY, { enabled: false });

    await act(async () => {
      limitSave.resolve(policyOf(5));
    });
  });

  it('creates a channel with its whole policy in one call and never patches it', async () => {
    vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [], statuses: [] });
    vi.mocked(createChannelBudget).mockResolvedValue(policyOf(2));

    render(<ChannelBudgetSection />);
    fireEvent.click(await screen.findByRole('button', { name: 'add' }));
    fireEvent.change(screen.getByPlaceholderText('channelKeyPlaceholder'), { target: { value: CHANNEL_KEY } });
    fireEvent.click(screen.getByRole('button', { name: 'save' }));

    await waitFor(() => expect(createChannelBudget).toHaveBeenCalledTimes(1));
    expect(createChannelBudget).toHaveBeenCalledWith(CHANNEL_KEY, {
      daily_limit_usd: 2,
      warning_threshold: 0.8,
      enabled: true,
      label: '',
    });
    expect(updateChannelBudget).not.toHaveBeenCalled();
  });

  // apiRequest shows the failure itself. What stays with the panel is the limit box: it must not keep a number that is
  // not in force, nor send it again when it is entered and left once more.
  it('puts the stored limit back when its save is rejected, and sends nothing when the box is left again', async () => {
    vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [policyOf(2)], statuses: [channelStatus(0)] });
    vi.mocked(updateChannelBudget).mockRejectedValue(new Error('rejected'));

    render(<ChannelBudgetSection />);
    const limitInput = await screen.findByDisplayValue<HTMLInputElement>('2');
    fireEvent.change(limitInput, { target: { value: '0' } });
    fireEvent.blur(limitInput);

    await waitFor(() => expect(limitInput.value).toBe('2'));
    fireEvent.blur(limitInput);
    expect(updateChannelBudget).toHaveBeenCalledTimes(1);
    expect(updateChannelBudget).toHaveBeenCalledWith(CHANNEL_KEY, { daily_limit_usd: 0 });
  });

  it('sends nothing and puts the stored limit back when the box is left empty', async () => {
    vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [policyOf(2)], statuses: [channelStatus(0)] });

    render(<ChannelBudgetSection />);
    const limitInput = await screen.findByDisplayValue<HTMLInputElement>('2');
    fireEvent.change(limitInput, { target: { value: '' } });
    fireEvent.blur(limitInput);

    await waitFor(() => expect(limitInput.value).toBe('2'));
    expect(updateChannelBudget).not.toHaveBeenCalled();
  });

  it('sends nothing when the typed limit is the one already in force', async () => {
    vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [policyOf(2)], statuses: [channelStatus(0)] });

    render(<ChannelBudgetSection />);
    const limitInput = await screen.findByDisplayValue<HTMLInputElement>('2');
    fireEvent.change(limitInput, { target: { value: '2.0' } });
    fireEvent.blur(limitInput);

    await waitFor(() => expect(limitInput.value).toBe('2'));
    expect(updateChannelBudget).not.toHaveBeenCalled();
  });

  // The box shows the limit in force whenever the user is not typing, and a stored save only changes it once the panel has
  // read the new policy back; leaving the typed number up until then keeps the old limit from flashing in between.
  it('keeps the typed limit on screen until the policy read back after a stored save arrives', async () => {
    const readBack = deferred<ChannelBudgetsResponse>();
    vi.mocked(getChannelBudgets)
      .mockResolvedValueOnce({ policies: [policyOf(2)], statuses: [channelStatus(0)] })
      .mockReturnValueOnce(readBack.promise);
    vi.mocked(updateChannelBudget).mockResolvedValue(policyOf(5));

    render(<ChannelBudgetSection />);
    const limitInput = await screen.findByDisplayValue<HTMLInputElement>('2');
    fireEvent.change(limitInput, { target: { value: '5' } });
    fireEvent.blur(limitInput);
    await waitFor(() => expect(getChannelBudgets).toHaveBeenCalledTimes(2));

    expect(limitInput.value).toBe('5');
    await act(async () => {
      readBack.resolve({ policies: [policyOf(5)], statuses: [channelStatus(0)] });
    });
    expect(limitInput.value).toBe('5');
  });
});
