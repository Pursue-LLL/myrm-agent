/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BranchSummaryCard } from '../BranchSummaryCard';
import type { BranchSummaryEntry } from '../compactionTypes';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

const mockBranchEntry: BranchSummaryEntry = {
  id: 'branch-card-1',
  sourceBranchId: 'branch-experiment-alpha',
  sourceBranchName: 'Alpha-Variant',
  forkedAtMessageId: 'msg-epoch-42',
  summary: 'Verified streaming token decoding latency over HTTP SSE vs WebSocket.',
  keyTakeaways: [
    'HTTP SSE is simpler with less reconnect overhead on corporate VPNs.',
    'WebSocket provides duplex cancellation without secondary RPC roundtrips.',
  ],
  createdAt: '2026-10-12T12:00:00Z',
};

describe('BranchSummaryCard component', () => {
  it('renders cross-branch experience flyline card details', () => {
    render(<BranchSummaryCard entry={mockBranchEntry} />);

    expect(screen.getByText('inheritedBadge')).toBeDefined();
    expect(screen.getByText('Alpha-Variant')).toBeDefined();
    expect(
      screen.getByText('Verified streaming token decoding latency over HTTP SSE vs WebSocket.'),
    ).toBeDefined();

    expect(screen.getByText('keyTakeawaysTitle')).toBeDefined();
    expect(
      screen.getByText('HTTP SSE is simpler with less reconnect overhead on corporate VPNs.'),
    ).toBeDefined();
    expect(
      screen.getByText('WebSocket provides duplex cancellation without secondary RPC roundtrips.'),
    ).toBeDefined();

    expect(screen.getByText(/msg-epoch-42/)).toBeDefined();
  });

  it('calls onWarpToSource callback when warp button is clicked', () => {
    const handleWarp = vi.fn();
    render(<BranchSummaryCard entry={mockBranchEntry} onWarpToSource={handleWarp} />);

    const warpBtn = screen.getByRole('button', { name: /warpToSource/i });
    fireEvent.click(warpBtn);

    expect(handleWarp).toHaveBeenCalledWith('branch-experiment-alpha');
  });

  it('dispatches custom event myrm:warp-to-branch when no callback provided', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    render(<BranchSummaryCard entry={mockBranchEntry} />);

    const warpBtn = screen.getByRole('button', { name: /warpToSource/i });
    fireEvent.click(warpBtn);

    expect(dispatchSpy).toHaveBeenCalled();
    const event = dispatchSpy.mock.calls[0][0] as CustomEvent;
    expect(event.type).toBe('myrm:warp-to-branch');
    expect(event.detail.branchId).toBe('branch-experiment-alpha');
  });
});
