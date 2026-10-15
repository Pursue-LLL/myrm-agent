import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { V1SpecSummaryModal } from '../V1SpecSummaryModal';
import { useClarificationQuestionnaireStore } from '../useClarificationQuestionnaireStore';

describe('V1SpecSummaryModal', () => {
  beforeEach(() => {
    useClarificationQuestionnaireStore.getState().reset();
  });

  it('未开启或无契约时返回 null 不渲染 DOM', () => {
    useClarificationQuestionnaireStore.setState({ isSpecModalOpen: false, activeSpecContract: null });
    const { container } = render(<V1SpecSummaryModal />);

    expect(container.firstChild).toBeNull();
  });

  it('打开时正常渲染契约目标、核心功能与明确排除项 Non-goals', () => {
    useClarificationQuestionnaireStore.setState({
      isSpecModalOpen: true,
      activeSpecContract: {
        productShape: '单页本地 Web 应用 (开箱即用)',
        coreCapabilities: ['参数计算', '本地导出'],
        nonGoals: ['排除多租户鉴权', '排除重型 PDF 生成'],
        generatedPromptText: '【克制 V1 需求规范与目标对齐协议】\n- 运行形态: 单页应用',
        totalAnswered: 4,
      },
    });

    render(<V1SpecSummaryModal />);

    expect(screen.getByTestId('v1-spec-summary-modal')).toBeInTheDocument();
    expect(screen.getByText('克制 V1 需求规范契约 (Goal Lock-in)')).toBeInTheDocument();
    expect(screen.getByText('单页本地 Web 应用 (开箱即用)')).toBeInTheDocument();
    expect(screen.getByText('参数计算')).toBeInTheDocument();
    expect(screen.getByText('排除多租户鉴权')).toBeInTheDocument();
    expect(screen.getByText('排除重型 PDF 生成')).toBeInTheDocument();
  });

  it('点击返回调整问卷关闭模态框', () => {
    useClarificationQuestionnaireStore.setState({
      isSpecModalOpen: true,
      activeSpecContract: {
        productShape: '单页 Web',
        coreCapabilities: ['核心计算'],
        nonGoals: ['不写后端'],
        generatedPromptText: 'prompt text',
        totalAnswered: 1,
      },
    });

    render(<V1SpecSummaryModal />);

    const backBtn = screen.getByText('返回调整问卷');
    fireEvent.click(backBtn);

    expect(useClarificationQuestionnaireStore.getState().isSpecModalOpen).toBe(false);
  });

  it('点击锁定契约并启动任务触发回调并更新状态', () => {
    const handleConfirm = vi.fn();
    useClarificationQuestionnaireStore.setState({
      isSpecModalOpen: true,
      activeSpecContract: {
        productShape: '单页 Web',
        coreCapabilities: ['核心计算'],
        nonGoals: ['不写后端'],
        generatedPromptText: 'prompt text',
        totalAnswered: 1,
      },
    });

    render(<V1SpecSummaryModal onConfirmLockIn={handleConfirm} />);

    const confirmBtn = screen.getByText('锁定契约并启动任务');
    fireEvent.click(confirmBtn);

    expect(handleConfirm).toHaveBeenCalled();
    expect(useClarificationQuestionnaireStore.getState().status).toBe('submitted');
  });
});
