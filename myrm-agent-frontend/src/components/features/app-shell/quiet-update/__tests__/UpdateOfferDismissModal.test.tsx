import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { UpdateOfferDismissModal } from '../UpdateOfferDismissModal';
import { useQuietMomentUpdateStore } from '../useQuietMomentUpdateStore';
import type { UpdateAvailabilitySnapshot } from '../quietMomentUpdateTypes';

describe('UpdateOfferDismissModal', () => {
  const mockSnapshot: UpdateAvailabilitySnapshot = {
    version: '2.1.0',
    readAt: 10_000,
  };

  beforeEach(() => {
    act(() => {
      useQuietMomentUpdateStore.setState({
        generation: 1,
        snapshot: mockSnapshot,
        isOfferVisible: true,
        isDismissModalOpen: true,
        dismissedVersions: [],
      });
    });
  });

  it('should not render anything when modal is closed or snapshot is missing', () => {
    act(() => {
      useQuietMomentUpdateStore.setState({ isDismissModalOpen: false });
    });
    const { container } = render(<UpdateOfferDismissModal />);
    expect(container.firstChild).toBeNull();

    act(() => {
      useQuietMomentUpdateStore.setState({ isDismissModalOpen: true, snapshot: null });
    });
    const { container: emptyContainer } = render(<UpdateOfferDismissModal />);
    expect(emptyContainer.firstChild).toBeNull();
  });

  it('should render modal content with default 4h snooze selected', () => {
    render(<UpdateOfferDismissModal />);

    expect(screen.getByTestId('update-offer-dismiss-modal')).toBeInTheDocument();
    expect(screen.getByText('调整更新提醒时机')).toBeInTheDocument();
    expect(screen.getByText(/稍后 4 小时再提醒/)).toBeInTheDocument();
    expect(screen.getByText(/明天此时再提醒/)).toBeInTheDocument();
    expect(screen.getByText(/跳过此版本/)).toBeInTheDocument();
  });

  it('should dismiss with 4 hours snooze by default when confirming', () => {
    const dismissSpy = vi.spyOn(useQuietMomentUpdateStore.getState(), 'dismissVersion');
    render(<UpdateOfferDismissModal />);

    const confirmBtn = screen.getByTestId('confirm-snooze-btn');
    fireEvent.click(confirmBtn);

    expect(dismissSpy).toHaveBeenCalledWith('2.1.0', 4);
    expect(useQuietMomentUpdateStore.getState().isDismissModalOpen).toBe(false);
  });

  it('should snooze for 24 hours when 24h option is chosen', () => {
    const dismissSpy = vi.spyOn(useQuietMomentUpdateStore.getState(), 'dismissVersion');
    render(<UpdateOfferDismissModal />);

    const radio24h = screen.getByRole('radio', { name: /明天此时再提醒/ });
    fireEvent.click(radio24h);

    const confirmBtn = screen.getByTestId('confirm-snooze-btn');
    fireEvent.click(confirmBtn);

    expect(dismissSpy).toHaveBeenCalledWith('2.1.0', 24);
  });

  it('should permanently skip version when skip option is chosen', () => {
    const dismissSpy = vi.spyOn(useQuietMomentUpdateStore.getState(), 'dismissVersion');
    render(<UpdateOfferDismissModal />);

    const radioSkip = screen.getByRole('radio', { name: /跳过此版本/ });
    fireEvent.click(radioSkip);

    const confirmBtn = screen.getByTestId('confirm-snooze-btn');
    fireEvent.click(confirmBtn);

    expect(dismissSpy).toHaveBeenCalledWith('2.1.0');
    const records = useQuietMomentUpdateStore.getState().dismissedVersions;
    expect(records.find((r) => r.version === '2.1.0')?.remindAfter).toBeUndefined();
  });

  it('should close modal on cancel button click', () => {
    render(<UpdateOfferDismissModal />);

    const cancelBtn = screen.getByRole('button', { name: '取消' });
    fireEvent.click(cancelBtn);

    expect(useQuietMomentUpdateStore.getState().isDismissModalOpen).toBe(false);
  });
});
