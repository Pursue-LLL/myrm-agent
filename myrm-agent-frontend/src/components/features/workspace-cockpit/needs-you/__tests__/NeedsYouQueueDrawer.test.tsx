import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { NeedsYouQueueDrawer } from '../NeedsYouQueueDrawer';
import { useNeedsYouQueueStore } from '../useNeedsYouQueueStore';

describe('NeedsYouQueueDrawer', () => {
  beforeEach(() => {
    act(() => {
      useNeedsYouQueueStore.getState().reset();
    });
  });

  it('should not render anything when drawer is closed', () => {
    const { container } = render(<NeedsYouQueueDrawer />);
    expect(container.firstChild).toBeNull();
  });

  it('should render items with whyStopped and whatWaitingFor details', () => {
    act(() => {
      useNeedsYouQueueStore.getState().registerInterruption({
        id: 'item-101',
        source: 'approval_pending',
        title: '执行 git push 需人工审批',
        whyStopped: '安全审计策略触发',
        whatWaitingFor: '确认是否推送到远程生产分支',
        chatId: 'chat-abc',
        urgency: 'urgent',
      });
      useNeedsYouQueueStore.getState().openDrawer();
    });

    render(<NeedsYouQueueDrawer />);

    expect(screen.getByTestId('needs-you-queue-drawer')).toBeInTheDocument();
    expect(screen.getByText('执行 git push 需人工审批')).toBeInTheDocument();
    expect(screen.getByText('安全审计策略触发')).toBeInTheDocument();
    expect(screen.getByText('确认是否推送到远程生产分支')).toBeInTheDocument();
    expect(screen.getByText('安全审批')).toBeInTheDocument();
    expect(screen.getByText('紧急')).toBeInTheDocument();
  });

  it('should handle single resolve action', () => {
    let itemId = '';
    act(() => {
      itemId = useNeedsYouQueueStore.getState().registerInterruption({
        source: 'goal_needs_review',
        title: '里程碑计划评审',
        whyStopped: '生成了新一阶段任务清单',
        whatWaitingFor: '用户授权',
        chatId: 'chat-abc',
        urgency: 'normal',
      });
      useNeedsYouQueueStore.getState().openDrawer();
    });

    render(<NeedsYouQueueDrawer />);

    const resolveBtn = screen.getByTestId(`resolve-btn-${itemId}`);
    act(() => {
      fireEvent.click(resolveBtn);
    });

    const item = useNeedsYouQueueStore.getState().items.find((i) => i.id === itemId);
    expect(item?.isHandled).toBe(true);
  });

  it('should trigger onNavigateToDeepLink when clicking deep link button', () => {
    const onNavigate = vi.fn();
    let itemId = '';
    act(() => {
      itemId = useNeedsYouQueueStore.getState().registerInterruption({
        source: 'unattended_clarification',
        title: '无人值守提问',
        whyStopped: '缺少数据库测试连接串',
        whatWaitingFor: '补充连接串',
        chatId: 'chat-xyz',
        urgency: 'normal',
      });
      useNeedsYouQueueStore.getState().openDrawer();
    });

    render(<NeedsYouQueueDrawer onNavigateToDeepLink={onNavigate} />);

    const deepLinkBtn = screen.getByTestId(`deep-link-btn-${itemId}`);
    fireEvent.click(deepLinkBtn);

    expect(onNavigate).toHaveBeenCalledTimes(1);
    expect(onNavigate).toHaveBeenCalledWith(
      expect.stringContaining('/chat/chat-xyz'),
      expect.objectContaining({ id: itemId }),
    );
  });

  it('should enforce reason requirement when dismissing an interruption to prevent silent drop', () => {
    let itemId = '';
    act(() => {
      itemId = useNeedsYouQueueStore.getState().registerInterruption({
        source: 'task_failed_retry',
        title: '构建失败待处理',
        whyStopped: '网络超时',
        whatWaitingFor: '确认是否重试',
        chatId: 'chat-abc',
        urgency: 'low',
      });
      useNeedsYouQueueStore.getState().openDrawer();
    });

    render(<NeedsYouQueueDrawer />);

    // 点击忽略按钮，打开理由弹窗
    const dismissBtn = screen.getByTestId(`dismiss-btn-${itemId}`);
    act(() => {
      fireEvent.click(dismissBtn);
    });

    expect(screen.getByTestId('dismiss-reason-modal')).toBeInTheDocument();

    // 未填理由直接确认应报错阻止
    const confirmBtn = screen.getByTestId('confirm-dismiss-reason-btn');
    act(() => {
      fireEvent.click(confirmBtn);
    });

    expect(screen.getByText('请填写忽略理由，防静默遗漏')).toBeInTheDocument();

    // 填写有效理由后提交
    const textarea = screen.getByTestId('dismiss-reason-textarea');
    act(() => {
      fireEvent.change(textarea, { target: { value: '已知网络波动，后台已自动切换备用源' } });
    });

    act(() => {
      fireEvent.click(confirmBtn);
    });

    const item = useNeedsYouQueueStore.getState().items.find((i) => i.id === itemId);
    expect(item?.isDismissed).toBe(true);
    expect(item?.dismissReason).toBe('已知网络波动，后台已自动切换备用源');
    expect(screen.queryByTestId('dismiss-reason-modal')).toBeNull();
  });
});
