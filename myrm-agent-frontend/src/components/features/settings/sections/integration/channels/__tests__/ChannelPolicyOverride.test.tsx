/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChannelPolicyOverride, type ChannelPolicyOverrideProps } from '../ChannelPolicyOverride';

const t: ChannelPolicyOverrideProps['t'] = (key) => key;

function renderOverride(overrides: Partial<ChannelPolicyOverrideProps> = {}) {
  const props: ChannelPolicyOverrideProps = {
    channel: 'telegram',
    globalDmPolicy: 'disabled',
    globalGroupPolicy: 'open',
    globalGroupTrigger: { mode: 'mention_only' },
    overrides: undefined,
    onOverride: vi.fn(),
    pairings: [],
    pairingsLoading: false,
    onAddPairing: vi.fn(),
    onDeletePairing: vi.fn(),
    onUpdatePairingStatus: vi.fn(),
    saving: false,
    t,
    ...overrides,
  };
  return render(<ChannelPolicyOverride {...props} />);
}

describe('ChannelPolicyOverride group trigger summary', () => {
  it('labels the summary region and the edit-global shortcut from translations', () => {
    renderOverride();

    expect(screen.getByRole('region', { name: 'groupTriggerRegionLabel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'editGlobalAria' })).toBeInTheDocument();
  });
});
