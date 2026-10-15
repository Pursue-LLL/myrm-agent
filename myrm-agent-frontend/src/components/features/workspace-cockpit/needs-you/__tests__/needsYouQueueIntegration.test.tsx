import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { NeedsYouQueueDrawer } from '../NeedsYouQueueDrawer';
import { AnchoredAlertNotificationBanner } from '../AnchoredAlertNotificationBanner';
import { useNeedsYouQueueStore } from '../useNeedsYouQueueStore';
import { mapNeedsYouToWorkspaceTaskItems } from '../needsYouQueueEngine';

describe('NeedsYouQueue Integration Flow', () => {
  beforeEach(() => {
    act(() => {
      useNeedsYouQueueStore.getState().reset();
    });
  });

  function IntegrationFixture() {
    return (
      <div>
        <AnchoredAlertNotificationBanner />
        <NeedsYouQueueDrawer />
      </div>
    );
  }

  it('should orchestrate alert banner trigger, batch handling and reason-enforced dismissal end-to-end', () => {
    let id1 = '';
    let id2 = '';
    let id3 = '';

    // 1. 模拟系统后台注册 3 类不同的中断源
    act(() => {
      id1 = useNeedsYouQueueStore.getState().registerInterruption({
        source: 'approval_pending',
        title: '敏感文件写操作审批',
        whyStopped: '安全规则要求写入配置文件需人类授权',
        whatWaitingFor: '确认是否覆盖 .env.local',
        chatId: 'chat-flow-1',
        urgency: 'urgent',
      });

      id2 = useNeedsYouQueueStore.getState().registerInterruption({
        source: 'goal_needs_review',
        title: '阶段二架构重构目标就绪',
        whyStopped: '生成了新一阶段任务拓扑',
        whatWaitingFor: '确认是否继续推进',
        chatId: 'chat-flow-2',
        urgency: 'normal',
      });

      id3 = useNeedsYouQueueStore.getState().registerInterruption({
        source: 'unattended_clarification',
        title: '长任务待答参数确认',
        whyStopped: '缺失目标集群命名空间',
        whatWaitingFor: '提供 namespace 字符串',
        chatId: 'chat-flow-3',
        urgency: 'low',
      });
    });

    // 2. 验证与既有四泳道无缝转换适配
    const currentItems = useNeedsYouQueueStore.getState().items;
    const taskItems = mapNeedsYouToWorkspaceTaskItems(currentItems);
    expect(taskItems.length).toBe(3);
    expect(taskItems.every((t) => t.swimlane === 'needs-you')).toBe(true);

    const { rerender } = render(<IntegrationFixture />);

    // 3. 验证常驻微横幅正确呈现待办总数与紧急状态
    expect(screen.getByTestId('anchored-alert-notification-banner')).toBeInTheDocument();
    expect(screen.getByText('3 项任务需要你')).toBeInTheDocument();
    expect(screen.getByText('1 紧急')).toBeInTheDocument();

    // 4. 用户点击「接手处理」，打开抽屉并聚焦到最新条目
    const openBtn = screen.getByTestId('open-needs-you-drawer-btn');
    act(() => {
      fireEvent.click(openBtn);
    });

    rerender(<IntegrationFixture />);
    expect(screen.getByTestId('needs-you-queue-drawer')).toBeInTheDocument();
    expect(screen.getByTestId(`needs-you-card-${id1}`)).toBeInTheDocument();
    expect(screen.getByTestId(`needs-you-card-${id2}`)).toBeInTheDocument();
    expect(screen.getByTestId(`needs-you-card-${id3}`)).toBeInTheDocument();

    // 5. 勾选前两个条目并执行批量通过
    act(() => {
      useNeedsYouQueueStore.getState().toggleSelectItem(id1);
      useNeedsYouQueueStore.getState().toggleSelectItem(id2);
    });

    rerender(<IntegrationFixture />);
    const batchApproveBtn = screen.getByTestId('batch-approve-btn');
    expect(batchApproveBtn).toHaveTextContent('批量通过 (2)');

    act(() => {
      fireEvent.click(batchApproveBtn);
    });

    rerender(<IntegrationFixture />);
    // id1 与 id2 已被处理，只剩 id3
    expect(screen.queryByTestId(`needs-you-card-${id1}`)).toBeNull();
    expect(screen.queryByTestId(`needs-you-card-${id2}`)).toBeNull();
    expect(screen.getByTestId(`needs-you-card-${id3}`)).toBeInTheDocument();

    // 6. 对最后一个待答卡点击忽略，并输入必填审计理由
    const dismissBtn = screen.getByTestId(`dismiss-btn-${id3}`);
    act(() => {
      fireEvent.click(dismissBtn);
    });

    rerender(<IntegrationFixture />);
    expect(screen.getByTestId('dismiss-reason-modal')).toBeInTheDocument();

    const textarea = screen.getByTestId('dismiss-reason-textarea');
    act(() => {
      fireEvent.change(textarea, { target: { value: '已在测试集群验证完毕，无需生产 namespace' } });
    });

    const confirmDismissBtn = screen.getByTestId('confirm-dismiss-reason-btn');
    act(() => {
      fireEvent.click(confirmDismissBtn);
    });

    rerender(<IntegrationFixture />);

    // 7. 所有任务接手完毕，抽屉呈现空态，横幅自动收起
    expect(screen.getByText(/所有阻塞性任务均已顺利接手/)).toBeInTheDocument();
    expect(screen.queryByTestId('anchored-alert-notification-banner')).toBeNull();
  });
});
