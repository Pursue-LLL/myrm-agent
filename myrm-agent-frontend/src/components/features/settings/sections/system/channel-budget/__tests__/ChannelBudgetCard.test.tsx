/**
 * [INPUT]
 * - ../ChannelBudgetCard (POS: card under test)
 * - ./channelBudgetTestKit (POS: shared fixtures)
 *
 * [OUTPUT]
 * - Test suite for what one channel card says about its channel: whether its group has been seen, what its buttons are
 *   called, and whether its audit is unfolded
 *
 * [POS]
 * A card is one of several that look alike, so its delete button names the channel, its audit toggle says whether it is
 * unfolded, and a channel no chat has reached yet says so without alarm.
 */
import { render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';
import ChannelBudgetCard from '../ChannelBudgetCard';
import { AUDIT_TOGGLE, CHANNEL_KEY, channelStatus, policyOf, stableT, trashName } from './channelBudgetTestKit';

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

function renderCard(props: Partial<ComponentProps<typeof ChannelBudgetCard>> = {}) {
  render(
    <ChannelBudgetCard
      status={channelStatus(0, CHANNEL_KEY, 'Team chat')}
      policy={policyOf(2, CHANNEL_KEY, 'Team chat')}
      audit={null}
      onSave={vi.fn()}
      onToggleAudit={vi.fn()}
      onRequestDelete={vi.fn()}
      {...props}
    />,
  );
}

describe('ChannelBudgetCard', () => {
  it('notes that no chat has reached the group yet, and only then', () => {
    renderCard({ status: channelStatus(0, CHANNEL_KEY, 'Team chat', false) });

    expect(screen.getByText('unseenGroupNote')).toBeInTheDocument();
  });

  it('has no note for a group that has a chat on record', () => {
    renderCard();

    expect(screen.queryByText('unseenGroupNote')).toBeNull();
  });

  it.each([
    { label: 'Team chat', expected: 'Team chat' },
    { label: '', expected: CHANNEL_KEY },
  ])('names the delete button after the channel: $expected', ({ label, expected }) => {
    renderCard({ status: channelStatus(0, CHANNEL_KEY, label) });

    expect(screen.getByRole('button', { name: trashName(expected) })).toBeInTheDocument();
  });

  it('says whether the audit is unfolded', () => {
    renderCard();
    expect(screen.getByRole('button', { name: AUDIT_TOGGLE })).toHaveAttribute('aria-expanded', 'false');
  });

  it('says the audit is unfolded once it is', () => {
    renderCard({ audit: { status: 'ready', entries: [], totalUsd: 0 } });

    expect(screen.getByRole('button', { name: AUDIT_TOGGLE })).toHaveAttribute('aria-expanded', 'true');
  });
});
