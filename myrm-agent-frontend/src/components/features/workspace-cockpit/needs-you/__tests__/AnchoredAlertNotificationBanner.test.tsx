import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { AnchoredAlertNotificationBanner } from '../AnchoredAlertNotificationBanner';
import { useNeedsYouQueueStore } from '../useNeedsYouQueueStore';

describe('AnchoredAlertNotificationBanner', () => {
  beforeEach(() => {
    act(() => {
      useNeedsYouQueueStore.getState().reset();
    });
  });

  it('should render nothing when there are no pending tasks or unread alerts', () => {
    const { container } = render(<AnchoredAlertNotificationBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('should render alert notification banner with pending count and urgent badge', () => {
    act(() => {
      useNeedsYouQueueStore.getState().registerInterruption({
        id: 'urg-1',
        source: 'approval_pending',
        title: '生产数据库迁移审批',
        whyStopped: '安全阈值',
        whatWaitingFor: '管理员授权',
        chatId: 'c1',
        urgency: 'urgent',
      });
      useNeedsYouQueueStore.getState().registerInterruption({
        id: 'norm-2',
        source: 'goal_needs_review',
        title: '里程碑完成',
        whyStopped: '等待评审',
        whatWaitingFor: '确认下一步',
        chatId: 'c2',
        urgency: 'normal',
      });
    });

    render(<AnchoredAlertNotificationBanner />);

    expect(screen.getByTestId('anchored-alert-notification-banner')).toBeInTheDocument();
    expect(screen.getByText('2 项任务需要你')).toBeInTheDocument();
    expect(screen.getByText('1 紧急')).toBeInTheDocument();
    expect(screen.getByText('里程碑完成')).toBeInTheDocument();
  });

  it('should open drawer with targeted item anchor on action button click', () => {
    let itemId = '';
    act(() => {
      itemId = useNeedsYouQueueStore.getState().registerInterruption({
        source: 'commitment_due',
        title: '定时研报发送到期',
        whyStopped: '定时器触发',
        whatWaitingFor: '确认发送',
        chatId: 'c3',
        urgency: 'normal',
      });
    });

    render(<AnchoredAlertNotificationBanner />);

    const openBtn = screen.getByTestId('open-needs-you-drawer-btn');
    act(() => {
      fireEvent.click(openBtn);
    });

    const state = useNeedsYouQueueStore.getState();
    expect(state.isDrawerOpen).toBe(true);
    expect(state.focusedItemId).toBe(itemId);
  });
});
