/**
 * [INPUT]
 * - ../ChannelBudgetSection (POS: panel under test)
 * - @/components/features/app-shell/confirm-dialog (real, not mocked)
 * - ./channelBudgetTestKit (POS: shared fixtures)
 *
 * [OUTPUT]
 * - Test suite for what the channel budget panel refuses to send: limits outside the stored range, and a channel deleted
 *   without a confirmation
 *
 * [POS]
 * A limit the server would reject is explained in the user's language before any request leaves; deleting a channel
 * removes its guard, so the trash button only asks.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChannelBudgetSection from '../ChannelBudgetSection';
import { CHANNEL_KEY, channelStatus, nextTick, policyOf, stableT, trashName } from './channelBudgetTestKit';
import { toast } from '@/lib/utils/toast';
import {
  createChannelBudget,
  deleteChannelBudget,
  getChannelBudgets,
  updateChannelBudget,
  type ChannelBudgetsResponse,
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
  getKnownChannelGroups: vi.fn().mockResolvedValue({ channel_keys: [] }),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { warning: vi.fn() },
}));

/** The message of a limit outside the range, with the bounds the server stores. */
const OUT_OF_RANGE = 'limitOutOfRange|0.01,10000';

describe('ChannelBudgetSection limit range', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  async function typeIntoLimitBox(typed: string) {
    vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [policyOf(2)], statuses: [channelStatus(0)] });
    vi.mocked(updateChannelBudget).mockResolvedValue(policyOf(2));

    render(<ChannelBudgetSection />);
    const limitInput = await screen.findByRole<HTMLInputElement>('spinbutton', { name: 'dailyLimit' });
    fireEvent.change(limitInput, { target: { value: typed } });
    await act(async () => {
      fireEvent.blur(limitInput);
      await nextTick();
    });
    return limitInput;
  }

  it.each(['0', '0.001', '10000.5', '-5'])(
    'sends nothing for the limit %s of a channel, says what the range is and shows the stored limit again',
    async (typed) => {
      const limitInput = await typeIntoLimitBox(typed);

      expect(updateChannelBudget).not.toHaveBeenCalled();
      expect(toast.warning).toHaveBeenCalledWith(OUT_OF_RANGE);
      expect(limitInput.value).toBe('2');
    },
  );

  it.each(['0.01', '10000'])('sends %s, an end of the range, without a warning', async (typed) => {
    await typeIntoLimitBox(typed);

    expect(updateChannelBudget).toHaveBeenCalledWith(CHANNEL_KEY, { daily_limit_usd: Number(typed) });
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it.each(['0', '10001'])(
    'keeps the add form as typed and sends nothing for the new channel limit %s',
    async (typed) => {
      vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [], statuses: [] });
      const user = userEvent.setup();

      render(<ChannelBudgetSection />);
      await user.click(await screen.findByRole('button', { name: 'add' }));
      await user.type(screen.getByPlaceholderText('channelKeyPlaceholder'), CHANNEL_KEY);
      const limitInput = screen.getByRole<HTMLInputElement>('spinbutton', { name: 'dailyLimit' });
      await user.tripleClick(limitInput);
      await user.keyboard(typed);
      await user.click(screen.getByRole('button', { name: 'save' }));

      expect(createChannelBudget).not.toHaveBeenCalled();
      expect(toast.warning).toHaveBeenCalledWith(OUT_OF_RANGE);
      expect(limitInput.value).toBe(typed);
      expect(screen.getByPlaceholderText('channelKeyPlaceholder')).toHaveValue(CHANNEL_KEY);
    },
  );
});

describe('ChannelBudgetSection deleting a channel', () => {
  const withLabel: ChannelBudgetsResponse = {
    policies: [policyOf(2, CHANNEL_KEY, 'Team chat')],
    statuses: [channelStatus(0, CHANNEL_KEY, 'Team chat')],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getChannelBudgets).mockResolvedValue(withLabel);
    vi.mocked(deleteChannelBudget).mockResolvedValue(undefined);
  });

  async function pressTrash() {
    render(<ChannelBudgetSection />);
    fireEvent.click(await screen.findByRole('button', { name: trashName('Team chat') }));
    await screen.findByText('deleteConfirmTitle');
  }

  it('only asks when the trash button is pressed, naming the channel, and sends nothing yet', async () => {
    await pressTrash();

    expect(screen.getByText('deleteConfirmDescription|Team chat')).toBeInTheDocument();
    expect(deleteChannelBudget).not.toHaveBeenCalled();
  });

  it('sends nothing and keeps the channel when the user cancels', async () => {
    await pressTrash();
    fireEvent.click(screen.getByTestId('confirm-dialog-cancel'));

    await waitFor(() => expect(screen.queryByText('deleteConfirmTitle')).toBeNull());
    expect(deleteChannelBudget).not.toHaveBeenCalled();
    expect(screen.getByText('Team chat')).toBeInTheDocument();
  });

  it('deletes that channel once confirmed and shows the list read back afterwards', async () => {
    vi.mocked(getChannelBudgets).mockResolvedValueOnce(withLabel).mockResolvedValue({ policies: [], statuses: [] });

    await pressTrash();
    fireEvent.click(screen.getByTestId('confirm-dialog-confirm'));

    await waitFor(() => expect(deleteChannelBudget).toHaveBeenCalledWith(CHANNEL_KEY));
    expect(await screen.findByText('empty')).toBeInTheDocument();
    expect(screen.queryByText('Team chat')).toBeNull();
  });

  it('closes the dialog and keeps the channel when the delete is rejected', async () => {
    vi.mocked(deleteChannelBudget).mockRejectedValue(new Error('rejected'));

    await pressTrash();
    fireEvent.click(screen.getByTestId('confirm-dialog-confirm'));

    await waitFor(() => expect(screen.queryByText('deleteConfirmTitle')).toBeNull());
    expect(deleteChannelBudget).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Team chat')).toBeInTheDocument();
  });
});
