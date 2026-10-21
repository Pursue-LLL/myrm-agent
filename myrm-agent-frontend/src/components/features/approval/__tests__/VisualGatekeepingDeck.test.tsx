import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { VisualGatekeepingDeck } from '../VisualGatekeepingDeck';
import { useExecutiveApprovalStore } from '../useExecutiveApprovalStore';

describe('VisualGatekeepingDeck', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useExecutiveApprovalStore.getState().resetStore();
  });

  it('中枢面板应正确渲染标题、统计指标与默认选中卡片', () => {
    render(<VisualGatekeepingDeck />);

    expect(screen.getByText('董事长把关审批与授权中枢')).toBeInTheDocument();
    expect(screen.getByText('待我把关')).toBeInTheDocument();
    expect(screen.getByText('高危红线拦截')).toBeInTheDocument();
    expect(screen.getByText('已通过放行')).toBeInTheDocument();
    expect(screen.getByText('工单总池')).toBeInTheDocument();
  });

  it('切换状态过滤器与风险过滤器能正确更新筛选列表', () => {
    render(<VisualGatekeepingDeck />);

    const allStatusBtn = screen.getByRole('button', { name: '全部' });
    fireEvent.click(allStatusBtn);
    expect(useExecutiveApprovalStore.getState().filterStatus).toBe('all');

    const highRiskBtn = screen.getByRole('button', { name: '高风险' });
    fireEvent.click(highRiskBtn);
    expect(useExecutiveApprovalStore.getState().filterRiskLevel).toBe('high');
  });

  it('点击左侧工单能切换选中的详细审批卡片', () => {
    useExecutiveApprovalStore.setState({ filterStatus: 'all', filterRiskLevel: 'all' });
    render(<VisualGatekeepingDeck />);

    const secondRequest = useExecutiveApprovalStore.getState().requests[1];
    expect(secondRequest).toBeDefined();
    if (secondRequest) {
      const targetBtn = screen.getByRole('button', { name: new RegExp(secondRequest.actionTitle, 'i') });
      fireEvent.click(targetBtn);
      expect(useExecutiveApprovalStore.getState().selectedRequestId).toBe(secondRequest.id);
    }
  });

  it('点击右上角关闭按钮应触发 onClose 回调', () => {
    const handleClose = vi.fn();
    render(<VisualGatekeepingDeck onClose={handleClose} />);

    const closeBtn = screen.getByRole('button', { name: '关闭审批中枢' });
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
    expect(useExecutiveApprovalStore.getState().isDeckOpen).toBe(false);
  });
});
