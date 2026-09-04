import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ContinualOverlayBadge, type ActiveOverlayItem } from '../ContinualOverlayBadge';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params?.count !== undefined) {
    return `${key}:${params.count}`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('ContinualOverlayBadge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when active overlay list is empty', () => {
    const { container } = render(<ContinualOverlayBadge overlays={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when all overlays have zero remaining turns', () => {
    const overlays: ActiveOverlayItem[] = [
      {
        overlayId: 'cso_1',
        shellType: 'prompt_patch',
        triggerReason: 'old trigger',
        remainingTurns: 0,
      },
    ];
    const { container } = render(<ContinualOverlayBadge overlays={overlays} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders active overlay badge with details and handles rollback click', async () => {
    const overlays: ActiveOverlayItem[] = [
      {
        overlayId: 'cso_active_1',
        shellType: 'subagent_config',
        triggerReason: 'Rate limit 429 on stripe_tool',
        remainingTurns: 3,
        advisoryText: 'Auto-retrying with exponential backoff',
      },
    ];

    const onRollbackMock = vi.fn().mockResolvedValue(undefined);

    render(<ContinualOverlayBadge overlays={overlays} onRollback={onRollbackMock} />);

    // Title and remaining turns should be visible
    expect(screen.getByText('activeTitle')).toBeInTheDocument();
    expect(screen.getByText('remainingTurns:3')).toBeInTheDocument();
    expect(screen.getByText('Auto-retrying with exponential backoff')).toBeInTheDocument();

    // Rollback button
    const rollbackBtn = screen.getByTitle('rollbackTooltip');
    fireEvent.click(rollbackBtn);

    await waitFor(() => {
      expect(onRollbackMock).toHaveBeenCalledWith('cso_active_1');
    });

    // Expand details
    const expandBtn = screen.getByLabelText('expand');
    fireEvent.click(expandBtn);

    expect(screen.getByText('howItWorks')).toBeInTheDocument();
    expect(screen.getByText('howItWorksDesc')).toBeInTheDocument();
  });
});
