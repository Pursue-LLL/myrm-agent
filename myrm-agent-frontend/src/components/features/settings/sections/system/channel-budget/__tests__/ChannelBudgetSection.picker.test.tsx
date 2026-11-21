/**
 * [INPUT]
 * - ../ChannelBudgetSection (POS: panel under test)
 * - ./channelBudgetTestKit (POS: shared fixtures)
 *
 * [OUTPUT]
 * - Test suite for how the add form of the channel budget panel offers the groups on record and takes what is typed
 *
 * [POS]
 * A group is picked instead of typed, and only groups without a channel are offered; the picker says nothing before the
 * server answered or when the lookup failed, and typing the key keeps working either way. Enter saves like the button.
 */
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChannelBudgetSection from '../ChannelBudgetSection';
import { deferred } from '@/test-utils/deferred';
import { CHANNEL_KEY, OTHER_CHANNEL_KEY, channelStatus, nextTick, policyOf, stableT } from './channelBudgetTestKit';
import {
  createChannelBudget,
  getChannelBudgets,
  getKnownChannelGroups,
  type KnownChannelGroupsResponse,
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

const THIRD_GROUP_KEY = 'slack:group:c-3';

async function openAddForm(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: 'add' }));
}

const keyBox = () => screen.getByPlaceholderText('channelKeyPlaceholder');

describe('ChannelBudgetSection group picker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [], statuses: [] });
    vi.mocked(createChannelBudget).mockResolvedValue(policyOf(2, OTHER_CHANNEL_KEY));
    vi.mocked(getKnownChannelGroups).mockResolvedValue({ channel_keys: [OTHER_CHANNEL_KEY, THIRD_GROUP_KEY] });
  });

  it('offers the groups on record, apart from those that already have a channel', async () => {
    vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [policyOf(2)], statuses: [channelStatus(0)] });
    vi.mocked(getKnownChannelGroups).mockResolvedValue({
      channel_keys: [CHANNEL_KEY, OTHER_CHANNEL_KEY, THIRD_GROUP_KEY],
    });
    const user = userEvent.setup();

    render(<ChannelBudgetSection />);
    await openAddForm(user);

    expect(await screen.findByRole('button', { name: OTHER_CHANNEL_KEY })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: THIRD_GROUP_KEY })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: CHANNEL_KEY })).toBeNull();
    expect(screen.getByText('knownGroupsTitle')).toBeInTheDocument();
  });

  it('puts the picked group in the key box and creates the channel with that key', async () => {
    const user = userEvent.setup();

    render(<ChannelBudgetSection />);
    await openAddForm(user);
    const chip = await screen.findByRole('button', { name: OTHER_CHANNEL_KEY });
    expect(chip).toHaveAttribute('aria-pressed', 'false');
    // Inside a form a button without a type submits it, and a browser would then save the channel on the pick.
    expect(chip).toHaveAttribute('type', 'button');
    await user.click(chip);

    expect(keyBox()).toHaveValue(OTHER_CHANNEL_KEY);
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: 'save' }));

    expect(createChannelBudget).toHaveBeenCalledWith(OTHER_CHANNEL_KEY, {
      daily_limit_usd: 2,
      warning_threshold: 0.8,
      enabled: true,
      label: '',
    });
  });

  it('asks for the groups again each time the form is opened', async () => {
    const user = userEvent.setup();

    render(<ChannelBudgetSection />);
    await openAddForm(user);
    await screen.findByRole('button', { name: OTHER_CHANNEL_KEY });
    await user.click(screen.getByRole('button', { name: 'cancel' }));
    await openAddForm(user);

    expect(getKnownChannelGroups).toHaveBeenCalledTimes(2);
  });

  it('says nothing about the groups until the answer is in, then that none is left to pick', async () => {
    const answer = deferred<KnownChannelGroupsResponse>();
    vi.mocked(getKnownChannelGroups).mockReturnValue(answer.promise);
    const user = userEvent.setup();

    render(<ChannelBudgetSection />);
    await openAddForm(user);

    expect(screen.queryByText('knownGroupsEmpty')).toBeNull();
    expect(screen.queryByText('knownGroupsTitle')).toBeNull();

    await act(async () => {
      answer.resolve({ channel_keys: [] });
      await nextTick();
    });

    expect(screen.getByText('knownGroupsEmpty')).toBeInTheDocument();
  });

  it('says none is left to pick when every group on record already has a channel', async () => {
    vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [policyOf(2)], statuses: [channelStatus(0)] });
    vi.mocked(getKnownChannelGroups).mockResolvedValue({ channel_keys: [CHANNEL_KEY] });
    const user = userEvent.setup();

    render(<ChannelBudgetSection />);
    await openAddForm(user);

    expect(await screen.findByText('knownGroupsEmpty')).toBeInTheDocument();
  });

  it('leaves the picker out when the lookup fails, and the key can still be typed', async () => {
    vi.mocked(getKnownChannelGroups).mockRejectedValue(new Error('offline'));
    const user = userEvent.setup();

    render(<ChannelBudgetSection />);
    await openAddForm(user);
    await act(async () => {
      await nextTick();
    });

    expect(screen.queryByText('knownGroupsEmpty')).toBeNull();
    expect(screen.queryByText('knownGroupsTitle')).toBeNull();
    await user.type(keyBox(), OTHER_CHANNEL_KEY);
    await user.click(screen.getByRole('button', { name: 'save' }));

    expect(createChannelBudget).toHaveBeenCalledWith(OTHER_CHANNEL_KEY, expect.any(Object));
  });
});

describe('ChannelBudgetSection add form keyboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getChannelBudgets).mockResolvedValue({ policies: [], statuses: [] });
    vi.mocked(createChannelBudget).mockResolvedValue(policyOf(2));
    vi.mocked(getKnownChannelGroups).mockResolvedValue({ channel_keys: [] });
  });

  it('saves on Enter like the Save button does, with the label trimmed', async () => {
    const user = userEvent.setup();

    render(<ChannelBudgetSection />);
    await openAddForm(user);
    await user.type(keyBox(), CHANNEL_KEY);
    await user.type(screen.getByPlaceholderText('labelPlaceholder'), '  Team chat  {Enter}');

    expect(createChannelBudget).toHaveBeenCalledTimes(1);
    expect(createChannelBudget).toHaveBeenCalledWith(CHANNEL_KEY, expect.objectContaining({ label: 'Team chat' }));
  });

  it('sends nothing on Enter while the key is empty', async () => {
    const user = userEvent.setup();

    render(<ChannelBudgetSection />);
    await openAddForm(user);
    await user.type(screen.getByPlaceholderText('labelPlaceholder'), 'Team chat{Enter}');

    expect(createChannelBudget).not.toHaveBeenCalled();
  });

  it('submits the form only through Save: Cancel is a plain button and picking a group saves nothing', async () => {
    vi.mocked(getKnownChannelGroups).mockResolvedValue({ channel_keys: [OTHER_CHANNEL_KEY] });
    const user = userEvent.setup();

    render(<ChannelBudgetSection />);
    await openAddForm(user);
    await user.click(await screen.findByRole('button', { name: OTHER_CHANNEL_KEY }));
    const cancel = screen.getByRole('button', { name: 'cancel' });
    expect(cancel).toHaveAttribute('type', 'button');
    expect(screen.getByRole('button', { name: 'save' })).toHaveAttribute('type', 'submit');
    await user.click(cancel);

    expect(createChannelBudget).not.toHaveBeenCalled();
  });
});
