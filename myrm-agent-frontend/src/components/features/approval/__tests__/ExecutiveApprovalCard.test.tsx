import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ExecutiveApprovalCard } from '../ExecutiveApprovalCard';
import { useExecutiveApprovalStore } from '../useExecutiveApprovalStore';
import type { ApprovalRequest } from '../executiveApprovalTypes';

describe('ExecutiveApprovalCard', () => {
  const mockPendingRequest: ApprovalRequest = {
    id: 'req-test-1',
    taskId: 't-1',
    agentId: 'a-1',
    agentName: '首席增长官',
    actionType: 'publish',
    actionTitle: '发布全网大促推文',
    targetChannel: '官方微博 @Myrm_AI',
    summary: '自动化宣发文案已就绪，请求审批发布。',
    proposedContent: '大促狂欢，限时 5 折起，快来体验！',
    riskLevel: 'high',
    riskReason: '涉及对外公开发布，直接影响品牌公信力。',
    createdAt: '2026-10-15T12:00:00Z',
    status: 'pending',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    useExecutiveApprovalStore.getState().resetStore();
    useExecutiveApprovalStore.setState({ requests: [mockPendingRequest] });
  });

  it('待审卡片应完整渲染智能体身份、风控徽章、拟执行内容与依据', () => {
    render(<ExecutiveApprovalCard request={mockPendingRequest} />);

    expect(screen.getByText('首席增长官')).toBeInTheDocument();
    expect(screen.getByText('高危操作把关')).toBeInTheDocument();
    expect(screen.getByText('发布全网大促推文')).toBeInTheDocument();
    expect(screen.getByText(/大促狂欢/)).toBeInTheDocument();
    expect(screen.getByText(/对外公开发布/)).toBeInTheDocument();
  });

  it('点击一键批准按钮应调用 approveRequest', () => {
    render(<ExecutiveApprovalCard request={mockPendingRequest} />);

    const approveBtn = screen.getByRole('button', { name: /一键批准执行/i });
    fireEvent.click(approveBtn);

    const storeItem = useExecutiveApprovalStore.getState().requests.find((r) => {
      return r.id === mockPendingRequest.id;
    });
    expect(storeItem?.status).toBe('approved');
  });

  it('点击驳回重做应展开输入框，提交后更新为 rejected 态', () => {
    render(<ExecutiveApprovalCard request={mockPendingRequest} />);

    const rejectBtn = screen.getByRole('button', { name: /驳回重做/i });
    fireEvent.click(rejectBtn);

    const input = screen.getByPlaceholderText(/请输入驳回修改意见/i);
    expect(input).toBeInTheDocument();

    fireEvent.change(input, { target: { value: '缺少退换货条款说明' } });
    const confirmBtn = screen.getByRole('button', { name: '确认驳回' });
    fireEvent.click(confirmBtn);

    const storeItem = useExecutiveApprovalStore.getState().requests.find((r) => {
      return r.id === mockPendingRequest.id;
    });
    expect(storeItem?.status).toBe('rejected');
    expect(storeItem?.feedbackComment).toBe('缺少退换货条款说明');
  });

  it('点击现场修改应展开编辑框，保存后触发 modifyAndApprove', () => {
    render(<ExecutiveApprovalCard request={mockPendingRequest} />);

    const editBtns = screen.getAllByRole('button', { name: /就地修改|现场修改/i });
    const editBtn = editBtns[0];
    if (editBtn) {
      fireEvent.click(editBtn);
    }

    const textarea = screen.getByLabelText('编辑拟执行内容');
    expect(textarea).toBeInTheDocument();

    fireEvent.change(textarea, { target: { value: '已加固修改后的安全内容' } });
    const saveBtn = screen.getByRole('button', { name: /保存并批准/i });
    fireEvent.click(saveBtn);

    const storeItem = useExecutiveApprovalStore.getState().requests.find((r) => {
      return r.id === mockPendingRequest.id;
    });
    expect(storeItem?.status).toBe('modified_approved');
    expect(storeItem?.modifiedContent).toBe('已加固修改后的安全内容');
  });

  it('已审批状态的卡片应正确展示对应放行或驳回标签', () => {
    const approvedRequest: ApprovalRequest = {
      ...mockPendingRequest,
      status: 'approved',
      feedbackComment: '董事长已核验放行',
    };

    render(<ExecutiveApprovalCard request={approvedRequest} />);
    expect(screen.getByText('董事长已批准执行')).toBeInTheDocument();
    expect(screen.getByText(/董事长已核验放行/)).toBeInTheDocument();
  });
});
