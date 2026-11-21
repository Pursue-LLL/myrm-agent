/**
 * [INPUT]
 * - ../ChannelBudgetSection (POS: panel under test)
 * - ./channelBudgetTestKit (POS: shared fixtures)
 *
 * [OUTPUT]
 * - Test suite for what the channel budget panel shows while it loads, when a load fails, and which answer wins when
 *   several are in flight
 *
 * [POS]
 * The panel never claims there are no channels before it has heard from the server, tells a failed load from an empty
 * list, lets only the newest answer change the screen, and tracks every save and audit request on its own.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChannelBudgetSection from '../ChannelBudgetSection';
import { deferred } from '@/test-utils/deferred';
import {
  CHANNEL_KEY,
  OTHER_CHANNEL_KEY,
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
  type ChannelAuditResponse,
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
}));

const oneChannel = (limitUsd: number): ChannelBudgetsResponse => ({
  policies: [policyOf(limitUsd)],
  statuses: [channelStatus(0)],
});

const twoChannels: ChannelBudgetsResponse = {
  policies: [policyOf(2), policyOf(2, OTHER_CHANNEL_KEY)],
  statuses: [channelStatus(0), channelStatus(0, OTHER_CHANNEL_KEY)],
};

const auditOf = (channelKey: string, entries: ChannelAuditEntry[]): ChannelAuditResponse => ({
  channel_key: channelKey,
  period_days: 7,
  entries,
  total_cost_usd: entries.reduce((sum, entry) => sum + entry.total_cost_usd, 0),
});

/** Types `typed` into `box` and leaves it, which sends the save. */
const saveLimit = (box: HTMLElement, typed: string) => {
  fireEvent.change(box, { target: { value: typed } });
  fireEvent.blur(box);
};

describe('ChannelBudgetSection loading the list', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('says nothing about an empty list while the first load is still running', async () => {
    const firstLoad = deferred<ChannelBudgetsResponse>();
    vi.mocked(getChannelBudgets).mockReturnValue(firstLoad.promise);

    render(<ChannelBudgetSection />);
    expect(screen.queryByText('empty')).toBeNull();

    await act(async () => {
      firstLoad.resolve({ policies: [], statuses: [] });
    });
    expect(screen.getByText('empty')).toBeInTheDocument();
  });

  it('tells a failed first load from an empty list, and loads again on Retry', async () => {
    vi.mocked(getChannelBudgets).mockRejectedValueOnce(new Error('offline')).mockResolvedValue(oneChannel(2));

    render(<ChannelBudgetSection />);

    expect(await screen.findByText('loadFailedTitle')).toBeInTheDocument();
    expect(screen.getByText('loadFailedDesc')).toBeInTheDocument();
    expect(screen.queryByText('empty')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'retry' }));

    expect(await screen.findByDisplayValue('2')).toBeInTheDocument();
    expect(screen.queryByText('loadFailedTitle')).toBeNull();
  });

  it('keeps the list on screen and says it may be out of date when a read-back fails', async () => {
    vi.mocked(getChannelBudgets).mockResolvedValueOnce(oneChannel(2)).mockRejectedValue(new Error('offline'));
    vi.mocked(updateChannelBudget).mockResolvedValue(policyOf(5));

    render(<ChannelBudgetSection />);
    saveLimit(await screen.findByRole('spinbutton', { name: 'dailyLimit' }), '5');

    expect(await screen.findByText('loadFailedStaleDesc')).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: 'dailyLimit' })).toBeInTheDocument();
  });
});

describe('ChannelBudgetSection read-backs in flight together', () => {
  let olderReadBack: ReturnType<typeof deferred<ChannelBudgetsResponse>>;
  let newerReadBack: ReturnType<typeof deferred<ChannelBudgetsResponse>>;

  /** Two saves in a row, so that two read-backs are in flight; returns the limit box. */
  async function saveTwice() {
    vi.mocked(getChannelBudgets)
      .mockResolvedValueOnce(oneChannel(2))
      .mockReturnValueOnce(olderReadBack.promise)
      .mockReturnValueOnce(newerReadBack.promise);
    vi.mocked(updateChannelBudget).mockResolvedValue(policyOf(5));

    render(<ChannelBudgetSection />);
    const limitInput = await screen.findByRole<HTMLInputElement>('spinbutton', { name: 'dailyLimit' });
    saveLimit(limitInput, '5');
    await waitFor(() => expect(getChannelBudgets).toHaveBeenCalledTimes(2));
    saveLimit(limitInput, '7');
    await waitFor(() => expect(getChannelBudgets).toHaveBeenCalledTimes(3));
    return limitInput;
  }

  beforeEach(() => {
    vi.clearAllMocks();
    olderReadBack = deferred<ChannelBudgetsResponse>();
    newerReadBack = deferred<ChannelBudgetsResponse>();
  });

  it('keeps what the newest read-back showed when an older one arrives later', async () => {
    const limitInput = await saveTwice();

    await act(async () => {
      newerReadBack.resolve(oneChannel(7));
      await nextTick();
    });
    expect(limitInput.value).toBe('7');

    await act(async () => {
      olderReadBack.resolve(oneChannel(5));
      await nextTick();
    });
    expect(limitInput.value).toBe('7');
  });

  it('does not let a read-back that failed long ago hide the list a newer one loaded', async () => {
    await saveTwice();

    await act(async () => {
      newerReadBack.resolve(oneChannel(7));
      await nextTick();
    });
    await act(async () => {
      olderReadBack.reject(new Error('offline'));
      await nextTick();
    });

    expect(screen.queryByText('loadFailedTitle')).toBeNull();
    expect(screen.getByRole('spinbutton', { name: 'dailyLimit' })).toHaveValue(7);
  });
});

describe('ChannelBudgetSection audit panel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getChannelBudgets).mockResolvedValue(twoChannels);
  });

  it('says the spending data could not be loaded, not that there is none, and loads again when unfolded again', async () => {
    vi.mocked(getChannelAudit)
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue(auditOf(CHANNEL_KEY, [auditEntry('alice', 3)]));

    render(<ChannelBudgetSection />);
    const [toggle] = await screen.findAllByText('auditDetails');
    fireEvent.click(toggle);

    expect(await screen.findByText('auditFailed')).toBeInTheDocument();
    expect(screen.queryByText('auditEmpty')).toBeNull();

    fireEvent.click(toggle);
    fireEvent.click(toggle);

    expect(await screen.findByText('alice')).toBeInTheDocument();
    expect(screen.queryByText('auditFailed')).toBeNull();
  });

  it('shows the channel unfolded last when an earlier audit answers late', async () => {
    const firstAudit = deferred<ChannelAuditResponse>();
    const secondAudit = deferred<ChannelAuditResponse>();
    vi.mocked(getChannelAudit).mockReturnValueOnce(firstAudit.promise).mockReturnValueOnce(secondAudit.promise);

    render(<ChannelBudgetSection />);
    const [firstToggle, secondToggle] = await screen.findAllByText('auditDetails');
    fireEvent.click(firstToggle);
    fireEvent.click(secondToggle);

    await act(async () => {
      secondAudit.resolve(auditOf(OTHER_CHANNEL_KEY, [auditEntry('bob', 1)]));
      await nextTick();
    });
    await act(async () => {
      firstAudit.resolve(auditOf(CHANNEL_KEY, [auditEntry('alice', 3)]));
      await nextTick();
    });

    expect(screen.getByText('bob')).toBeInTheDocument();
    expect(screen.queryByText('alice')).toBeNull();
  });
});

describe('ChannelBudgetSection saves in flight together', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps a channel busy until its own save has settled, whatever the other channel does', async () => {
    const saveOfFirst = deferred<ChannelBudgetPolicy>();
    const saveOfSecond = deferred<ChannelBudgetPolicy>();
    vi.mocked(getChannelBudgets).mockResolvedValue(twoChannels);
    vi.mocked(updateChannelBudget).mockReturnValueOnce(saveOfFirst.promise).mockReturnValueOnce(saveOfSecond.promise);

    render(<ChannelBudgetSection />);
    const [firstBox, secondBox] = await screen.findAllByRole('spinbutton', { name: 'dailyLimit' });
    const [firstTrash, secondTrash] = screen.getAllByRole('button', { name: 'delete' });
    saveLimit(firstBox, '3');
    saveLimit(secondBox, '4');
    expect(firstTrash).toBeDisabled();
    expect(secondTrash).toBeDisabled();

    await act(async () => {
      saveOfSecond.resolve(policyOf(4, OTHER_CHANNEL_KEY));
      await nextTick();
    });

    expect(secondTrash).toBeEnabled();
    expect(firstTrash).toBeDisabled();

    await act(async () => {
      saveOfFirst.resolve(policyOf(3));
      await nextTick();
    });
    expect(firstTrash).toBeEnabled();
  });

  it('keeps Save of the add form off while its own request is in flight, even when a channel save settles', async () => {
    const create = deferred<ChannelBudgetPolicy>();
    vi.mocked(getChannelBudgets).mockResolvedValue(oneChannel(2));
    vi.mocked(createChannelBudget).mockReturnValue(create.promise);
    vi.mocked(updateChannelBudget).mockResolvedValue(policyOf(5));

    render(<ChannelBudgetSection />);
    const limitBox = await screen.findByRole('spinbutton', { name: 'dailyLimit' });
    fireEvent.click(screen.getByRole('button', { name: 'add' }));
    fireEvent.change(screen.getByPlaceholderText('channelKeyPlaceholder'), { target: { value: OTHER_CHANNEL_KEY } });
    fireEvent.click(screen.getByRole('button', { name: 'save' }));
    expect(screen.getByRole('button', { name: 'save' })).toBeDisabled();

    await act(async () => {
      saveLimit(limitBox, '5');
      await nextTick();
    });

    expect(screen.getByRole('button', { name: 'save' })).toBeDisabled();
    await act(async () => {
      create.resolve(policyOf(2, OTHER_CHANNEL_KEY));
      await nextTick();
    });
  });
});
