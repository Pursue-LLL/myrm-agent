import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { QuietMomentUpdateBanner } from '../QuietMomentUpdateBanner';
import { useQuietMomentUpdateStore } from '../useQuietMomentUpdateStore';
import type { UpdateAvailabilitySnapshot } from '../quietMomentUpdateTypes';

describe('QuietMomentUpdateBanner', () => {
  const mockSnapshot: UpdateAvailabilitySnapshot = {
    version: '1.8.0',
    currentVersion: '1.7.5',
    releaseDate: '2026-10-15',
    releaseNotes: '优化推理时延并修复后台工作流偶发中断问题',
    downloadSizeMb: 52.4,
    readAt: 10_000,
    isCritical: true,
  };

  beforeEach(() => {
    act(() => {
      useQuietMomentUpdateStore.setState({
        generation: 1,
        snapshot: mockSnapshot,
        isOfferVisible: true,
        activeTipId: 'update-offer:1.8.0',
        isDismissModalOpen: false,
        isWindowFocused: true,
        isDocumentVisible: true,
        hasActiveStreamingOrTask: false,
        hasBlockingSurface: false,
        isInstallingBusy: false,
        connectionMode: 'local',
        lastTypedAt: 0,
        typingGraceMs: 5000,
      });
    });
  });

  it('should not render anything when offer is not visible or snapshot is null', () => {
    act(() => {
      useQuietMomentUpdateStore.setState({ isOfferVisible: false });
    });
    const { container } = render(<QuietMomentUpdateBanner />);
    expect(container.firstChild).toBeNull();

    act(() => {
      useQuietMomentUpdateStore.setState({ isOfferVisible: true, snapshot: null });
    });
    const { container: emptyContainer } = render(<QuietMomentUpdateBanner />);
    expect(emptyContainer.firstChild).toBeNull();
  });

  it('should render update banner details properly when visible', () => {
    render(<QuietMomentUpdateBanner />);

    expect(screen.getByTestId('quiet-moment-update-banner')).toBeInTheDocument();
    expect(screen.getByText('v1.8.0')).toBeInTheDocument();
    expect(screen.getByText(/当前版本: v1.7.5/)).toBeInTheDocument();
    expect(screen.getByText(/52.4 MB/)).toBeInTheDocument();
    expect(screen.getByText('建议更新')).toBeInTheDocument();
    expect(screen.getByText('优化推理时延并修复后台工作流偶发中断问题')).toBeInTheDocument();
  });

  it('should trigger closeOffer when clicking the close button', () => {
    render(<QuietMomentUpdateBanner />);

    const closeBtn = screen.getByTestId('quiet-update-close-btn');
    fireEvent.click(closeBtn);

    expect(useQuietMomentUpdateStore.getState().isOfferVisible).toBe(false);
  });

  it('should open dismiss snooze modal when clicking snooze button', () => {
    render(<QuietMomentUpdateBanner />);

    const snoozeBtn = screen.getByTestId('quiet-update-snooze-btn');
    fireEvent.click(snoozeBtn);

    expect(useQuietMomentUpdateStore.getState().isDismissModalOpen).toBe(true);
  });

  it('should invoke onUpdateAction on confirm update click', async () => {
    const onUpdateAction = vi.fn();
    render(<QuietMomentUpdateBanner onUpdateAction={onUpdateAction} />);

    const applyBtn = screen.getByTestId('quiet-update-apply-btn');
    fireEvent.click(applyBtn);

    expect(onUpdateAction).toHaveBeenCalledTimes(1);
    expect(useQuietMomentUpdateStore.getState().isOfferVisible).toBe(false);
  });

  it('should navigate to release details when link clicked', () => {
    const onNavigateDetails = vi.fn();
    render(<QuietMomentUpdateBanner onNavigateDetails={onNavigateDetails} />);

    const detailsBtn = screen.getByTestId('quiet-update-details-btn');
    fireEvent.click(detailsBtn);

    expect(onNavigateDetails).toHaveBeenCalledTimes(1);
  });
});
