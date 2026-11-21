/**
 * [INPUT]
 * - ../ChannelBudgetSection (POS: panel under test)
 * - ./channelBudgetTestKit (POS: shared fixtures)
 *
 * [OUTPUT]
 * - Test suite for the audit, the saves, the add form and the limit boxes of the channel budget panel
 *
 * [POS]
 * Pins what the panel sends and shows once a channel is configured: the audit bars, the patch of each edit, the whole
 * policy of a new channel, and how a limit box and the add form handle what is typed.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChannelBudgetSection from '../ChannelBudgetSection';
import { deferred } from '@/test-utils/deferred';
import {
  AUDIT_TOGGLE,
  CHANNEL_KEY,
  auditEntry,
  channelStatus,
  nextTick,
  policyOf,
  stableT,
} from './channelBudgetTestKit';
import {
  createChannelBudget,
  getChannelAudit,
  getChannelBudgets,
  updateChannelBudget,
  type ChannelAuditEntry,
  type ChannelBudgetPolicy,
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

type PolicySave = ReturnType<typeof deferred<ChannelBudgetPolicy>>;

async function openAudit(todayCostUsd: number, entries: ChannelAuditEntry[]) {
  vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [], statuses: [channelStatus(todayCostUsd)] });
  vi.mocked(getChannelAudit).mockResolvedValue({
    channel_key: CHANNEL_KEY,
    period_days: 7,
    entries,
    total_cost_usd: entries.reduce((sum, entry) => sum + entry.total_cost_usd, 0),
  });

  render(<ChannelBudgetSection />);
  fireEvent.click(await screen.findByText(AUDIT_TOGGLE));
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
    fireEvent.change(limitInput, { target: { value: '3' } });
    fireEvent.blur(limitInput);

    await waitFor(() => expect(limitInput.value).toBe('2'));
    fireEvent.blur(limitInput);
    expect(updateChannelBudget).toHaveBeenCalledTimes(1);
    expect(updateChannelBudget).toHaveBeenCalledWith(CHANNEL_KEY, { daily_limit_usd: 3 });
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

  // A stored save only changes the box once the panel has read the new policy back; leaving the typed number up until
  // then keeps the old limit from flashing in between.
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

  // What is typed while a save is in flight is the next edit, not the saved one: the save clears only the text it
  // handled, so keystrokes are not swallowed and leaving the box again sends what is on screen.
  it.each([
    {
      outcome: 'stored',
      sent: '7',
      typedMore: '76',
      inForce: 7,
      settle: (save: PolicySave) => save.resolve(policyOf(7)),
    },
    {
      outcome: 'rejected',
      sent: '9',
      typedMore: '91',
      inForce: 2,
      settle: (save: PolicySave) => save.reject(new Error('rejected')),
    },
  ])(
    'keeps what is typed while a $outcome save is in flight and sends it when the box is left again',
    async ({ sent, typedMore, inForce, settle }) => {
      const save = deferred<ChannelBudgetPolicy>();
      vi.mocked(getChannelBudgets)
        .mockResolvedValueOnce({ policies: [policyOf(2)], statuses: [channelStatus(0)] })
        .mockResolvedValue({ policies: [policyOf(inForce)], statuses: [channelStatus(0)] });
      vi.mocked(updateChannelBudget)
        .mockReturnValueOnce(save.promise)
        .mockResolvedValue(policyOf(Number(typedMore)));

      render(<ChannelBudgetSection />);
      const limitInput = await screen.findByDisplayValue<HTMLInputElement>('2');
      fireEvent.change(limitInput, { target: { value: sent } });
      fireEvent.blur(limitInput);
      fireEvent.change(limitInput, { target: { value: typedMore } });
      await act(async () => {
        settle(save);
        await nextTick();
      });

      expect(limitInput.value).toBe(typedMore);
      await act(async () => {
        fireEvent.blur(limitInput);
        await nextTick();
      });
      expect(updateChannelBudget).toHaveBeenLastCalledWith(CHANNEL_KEY, { daily_limit_usd: Number(typedMore) });
    },
  );
});

describe('ChannelBudgetSection add form', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [], statuses: [] });
    vi.mocked(createChannelBudget).mockResolvedValue(policyOf(2));
  });

  /** Opens the add form with a channel key typed and returns its limit box, which starts at the default of 2. */
  async function openAddForm(user: ReturnType<typeof userEvent.setup>) {
    render(<ChannelBudgetSection />);
    await user.click(await screen.findByRole('button', { name: 'add' }));
    await user.type(screen.getByPlaceholderText('channelKeyPlaceholder'), CHANNEL_KEY);
    return screen.getByDisplayValue<HTMLInputElement>('2');
  }

  // A number box that cannot be emptied turns every edit into an append: End, Backspace, 5 has to leave 5, not 25.
  it('lets the limit of a new channel be cleared and typed again', async () => {
    const user = userEvent.setup();
    const limitInput = await openAddForm(user);

    await user.click(limitInput);
    await user.keyboard('{End}{Backspace}5');
    await user.click(screen.getByRole('button', { name: 'save' }));

    await waitFor(() => expect(createChannelBudget).toHaveBeenCalledTimes(1));
    expect(createChannelBudget).toHaveBeenCalledWith(CHANNEL_KEY, expect.objectContaining({ daily_limit_usd: 5 }));
  });

  it('takes a decimal limit typed from scratch', async () => {
    const user = userEvent.setup();
    const limitInput = await openAddForm(user);

    await user.tripleClick(limitInput);
    await user.keyboard('0.5');
    await user.click(screen.getByRole('button', { name: 'save' }));

    await waitFor(() => expect(createChannelBudget).toHaveBeenCalledTimes(1));
    expect(createChannelBudget).toHaveBeenCalledWith(CHANNEL_KEY, expect.objectContaining({ daily_limit_usd: 0.5 }));
  });

  it('keeps Save off while the limit box is empty', async () => {
    const user = userEvent.setup();
    const limitInput = await openAddForm(user);

    await user.click(limitInput);
    await user.keyboard('{End}{Backspace}');

    expect(limitInput.value).toBe('');
    expect(screen.getByRole('button', { name: 'save' })).toBeDisabled();
    expect(createChannelBudget).not.toHaveBeenCalled();
  });

  it('starts the next new channel at the default limit again once one has been added', async () => {
    const user = userEvent.setup();
    const limitInput = await openAddForm(user);

    await user.tripleClick(limitInput);
    await user.keyboard('5');
    await user.click(screen.getByRole('button', { name: 'save' }));
    await waitFor(() => expect(createChannelBudget).toHaveBeenCalledTimes(1));
    await user.click(await screen.findByRole('button', { name: 'add' }));

    expect(screen.getByDisplayValue('2')).toBeInTheDocument();
  });

  it('keeps the form open, with what was typed, when the new channel is rejected', async () => {
    vi.mocked(createChannelBudget).mockRejectedValue(new Error('refused'));
    const user = userEvent.setup();
    const limitInput = await openAddForm(user);

    await user.tripleClick(limitInput);
    await user.keyboard('4');
    await user.type(screen.getByPlaceholderText('labelPlaceholder'), 'Ops');
    await user.click(screen.getByRole('button', { name: 'save' }));

    await waitFor(() => expect(createChannelBudget).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole('button', { name: 'save' })).toBeEnabled());
    expect(screen.getByPlaceholderText('channelKeyPlaceholder')).toHaveValue(CHANNEL_KEY);
    expect(screen.getByPlaceholderText('labelPlaceholder')).toHaveValue('Ops');
    expect(limitInput.value).toBe('4');
  });

  it('closes the form only once the list has been read back with the new channel', async () => {
    const readBack = deferred<ChannelBudgetsResponse>();
    const user = userEvent.setup();
    const limitInput = await openAddForm(user);
    vi.mocked(getChannelBudgets).mockReturnValueOnce(readBack.promise);

    await user.click(screen.getByRole('button', { name: 'save' }));
    await waitFor(() => expect(getChannelBudgets).toHaveBeenCalledTimes(2));
    expect(limitInput).toBeInTheDocument();

    await act(async () => {
      readBack.resolve({ policies: [policyOf(2)], statuses: [channelStatus(0)] });
      await nextTick();
    });

    expect(screen.queryByPlaceholderText('channelKeyPlaceholder')).toBeNull();
    expect(screen.getByText(CHANNEL_KEY)).toBeInTheDocument();
  });
});

describe('ChannelBudgetSection limit boxes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /** A limit box has to name itself and accept every amount the server accepts, not only the ones on a step grid. */
  const expectNamedAndAnyAmountValid = (limitInput: HTMLInputElement) => {
    for (const amount of ['0.01', '2', '7.25', '10000']) {
      fireEvent.change(limitInput, { target: { value: amount } });
      expect(limitInput.validity.valid).toBe(true);
    }
  };

  it('names the limit box of a channel and takes any amount in range', async () => {
    vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [policyOf(2)], statuses: [channelStatus(0)] });

    render(<ChannelBudgetSection />);

    expectNamedAndAnyAmountValid(await screen.findByRole<HTMLInputElement>('spinbutton', { name: 'dailyLimit' }));
  });

  it('names the limit box of a new channel and takes any amount in range', async () => {
    vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [], statuses: [] });

    render(<ChannelBudgetSection />);
    fireEvent.click(await screen.findByRole('button', { name: 'add' }));

    expectNamedAndAnyAmountValid(screen.getByRole<HTMLInputElement>('spinbutton', { name: 'dailyLimit' }));
  });
});
