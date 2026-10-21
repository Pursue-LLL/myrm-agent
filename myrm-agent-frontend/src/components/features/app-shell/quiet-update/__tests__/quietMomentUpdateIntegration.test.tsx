import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { QuietMomentUpdateBanner } from '../QuietMomentUpdateBanner';
import { UpdateOfferDismissModal } from '../UpdateOfferDismissModal';
import { useQuietMomentUpdateStore } from '../useQuietMomentUpdateStore';
import type { UpdateAvailabilitySnapshot } from '../quietMomentUpdateTypes';

describe('QuietMomentUpdate Integration Flow', () => {
  const newReleaseSnapshot: UpdateAvailabilitySnapshot = {
    version: '2.5.0',
    currentVersion: '2.4.2',
    releaseDate: '2026-10-15',
    releaseNotes: '支持全双工语音中断与超低延迟首包渲染',
    downloadSizeMb: 68.2,
    readAt: 10_000,
    isCritical: false,
  };

  beforeEach(() => {
    act(() => {
      useQuietMomentUpdateStore.setState({
        generation: 1,
        snapshot: newReleaseSnapshot,
        isOfferVisible: false,
        activeTipId: null,
        lastOfferedAt: undefined,
        dismissedVersions: [],
        isDismissModalOpen: false,
        lastTypedAt: 10_000,
        typingGraceMs: 5000,
        isWindowFocused: true,
        isDocumentVisible: true,
        hasActiveStreamingOrTask: false,
        hasBlockingSurface: false,
        isInstallingBusy: false,
        connectionMode: 'local',
      });
    });
  });

  it('should orchestrate quiet moment detection, user snooze flow and gateway reset end-to-end', () => {
    const onUpdateAction = vi.fn();
    const { rerender } = render(
      <>
        <QuietMomentUpdateBanner onUpdateAction={onUpdateAction} />
        <UpdateOfferDismissModal />
      </>,
    );

    // 1. 用户近期打字中（打字距今 2 秒，小于 5 秒宽限期）
    act(() => {
      useQuietMomentUpdateStore.setState({ lastTypedAt: 12_000 });
    });
    let eligible = false;
    act(() => {
      eligible = useQuietMomentUpdateStore.getState().checkQuietMoment(14_000);
    });
    expect(eligible).toBe(false);
    expect(screen.queryByTestId('quiet-moment-update-banner')).toBeNull();

    // 2. 5 秒过去，进入真正安静时刻
    act(() => {
      eligible = useQuietMomentUpdateStore.getState().checkQuietMoment(20_000);
    });
    expect(eligible).toBe(true);

    rerender(
      <>
        <QuietMomentUpdateBanner onUpdateAction={onUpdateAction} />
        <UpdateOfferDismissModal />
      </>,
    );

    expect(screen.getByTestId('quiet-moment-update-banner')).toBeInTheDocument();
    expect(screen.getByText('v2.5.0')).toBeInTheDocument();

    // 3. 用户点击稍后提醒，唤起二级选项弹窗
    const snoozeBtn = screen.getByTestId('quiet-update-snooze-btn');
    fireEvent.click(snoozeBtn);

    rerender(
      <>
        <QuietMomentUpdateBanner onUpdateAction={onUpdateAction} />
        <UpdateOfferDismissModal />
      </>,
    );

    expect(screen.getByTestId('update-offer-dismiss-modal')).toBeInTheDocument();

    // 4. 选择稍后 4 小时并确认
    const confirmSnoozeBtn = screen.getByTestId('confirm-snooze-btn');
    fireEvent.click(confirmSnoozeBtn);

    rerender(
      <>
        <QuietMomentUpdateBanner onUpdateAction={onUpdateAction} />
        <UpdateOfferDismissModal />
      </>,
    );

    expect(screen.queryByTestId('quiet-moment-update-banner')).toBeNull();
    expect(screen.queryByTestId('update-offer-dismiss-modal')).toBeNull();

    // 5. 处于 4 小时推迟期内，再次检查不重复弹出
    let checkDuringSnooze = false;
    act(() => {
      checkDuringSnooze = useQuietMomentUpdateStore.getState().checkQuietMoment(21_000);
    });
    expect(checkDuringSnooze).toBe(false);

    // 6. 连接切换导致 generation 递增重置
    act(() => {
      useQuietMomentUpdateStore.getState().setConnectionMode('cloud');
    });
    expect(useQuietMomentUpdateStore.getState().generation).toBe(2);
    expect(useQuietMomentUpdateStore.getState().snapshot).toBeNull();
  });
});
