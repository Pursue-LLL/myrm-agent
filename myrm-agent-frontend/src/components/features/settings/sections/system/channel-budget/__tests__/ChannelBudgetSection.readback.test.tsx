/**
 * [INPUT]
 * - ../ChannelBudgetSection (POS: panel under test)
 * - @/components/features/app-shell/confirm-dialog (real, not mocked)
 * - ./channelBudgetTestKit (POS: shared fixtures)
 *
 * [OUTPUT]
 * - Test suite for what the channel budget panel does after the server refuses a write
 *
 * [POS]
 * A refused write often means the list on screen is out of date (the channel was removed or changed from another page),
 * so the panel reads the list back after every write, stored or not, and shows what the server holds now.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChannelBudgetSection from '../ChannelBudgetSection';
import { CHANNEL_KEY, channelStatus, policyOf, stableT, trashName } from './channelBudgetTestKit';
import {
  createChannelBudget,
  deleteChannelBudget,
  getChannelBudgets,
  getKnownChannelGroups,
  updateChannelBudget,
} from '@/services/budget';

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/budget', () => ({
  getChannelBudgets: vi.fn(),
  createChannelBudget: vi.fn(),
  updateChannelBudget: vi.fn(),
  deleteChannelBudget: vi.fn(),
  getChannelAudit: vi.fn(),
  getKnownChannelGroups: vi.fn(),
}));

describe('ChannelBudgetSection after a refused write', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getKnownChannelGroups).mockResolvedValue({ channel_keys: [] });
  });

  it('shows the limit stored now when a limit save is refused', async () => {
    vi.mocked(getChannelBudgets)
      .mockResolvedValueOnce({ policies: [policyOf(2)], statuses: [channelStatus(0)] })
      .mockResolvedValue({ policies: [policyOf(3)], statuses: [channelStatus(0)] });
    vi.mocked(updateChannelBudget).mockRejectedValue(new Error('refused'));

    render(<ChannelBudgetSection />);
    const limitInput = await screen.findByDisplayValue<HTMLInputElement>('2');
    fireEvent.change(limitInput, { target: { value: '5' } });
    fireEvent.blur(limitInput);

    await waitFor(() => expect(limitInput.value).toBe('3'));
    expect(getChannelBudgets).toHaveBeenCalledTimes(2);
  });

  it('drops a channel from the list when its delete is refused because it is already gone', async () => {
    vi.mocked(getChannelBudgets)
      .mockResolvedValueOnce({ policies: [policyOf(2)], statuses: [channelStatus(0)] })
      .mockResolvedValue({ policies: [], statuses: [] });
    vi.mocked(deleteChannelBudget).mockRejectedValue(new Error('not found'));

    render(<ChannelBudgetSection />);
    fireEvent.click(await screen.findByRole('button', { name: trashName(CHANNEL_KEY) }));
    fireEvent.click(await screen.findByTestId('confirm-dialog-confirm'));

    expect(await screen.findByText('empty')).toBeInTheDocument();
    expect(screen.queryByText(CHANNEL_KEY)).toBeNull();
  });

  it('lists the channel the server holds when a new channel is refused, and keeps the form as typed', async () => {
    vi.mocked(getChannelBudgets)
      .mockResolvedValueOnce({ policies: [], statuses: [] })
      .mockResolvedValue({ policies: [policyOf(2)], statuses: [channelStatus(0)] });
    vi.mocked(createChannelBudget).mockRejectedValue(new Error('refused'));
    const user = userEvent.setup();

    render(<ChannelBudgetSection />);
    await user.click(await screen.findByRole('button', { name: 'add' }));
    await user.type(screen.getByPlaceholderText('channelKeyPlaceholder'), CHANNEL_KEY);
    await user.click(screen.getByRole('button', { name: 'save' }));

    expect(await screen.findByText(CHANNEL_KEY)).toBeInTheDocument();
    expect(screen.getByPlaceholderText('channelKeyPlaceholder')).toHaveValue(CHANNEL_KEY);
  });
});
