import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { OnDemandDecisionModal } from '../OnDemandDecisionModal';
import { useOnDemandConfirmationStore } from '../useOnDemandConfirmationStore';
import { OnDemandDecisionInterrupt } from '../onDemandConfirmationTypes';

describe('OnDemandDecisionModal 组件单测', () => {
  const sampleInterrupt: OnDemandDecisionInterrupt = {
    interruptId: 'int-301',
    taskId: 'task-999',
    prompt: '确认小红书笔记发布渠道与样式',
    contextSummary: '当前正在处理图文排版，需要选择具体的视觉风格定位',
    options: [
      { id: 'A', label: '图文轮播模板 A', description: '适合多图细节展示' },
      { id: 'B', label: '单张长图模板 B', description: '适合故事性长文本', isRecommended: true },
      { id: 'C', label: '网格九宫格模板 C' },
    ],
    allowCustomInput: true,
  };

  beforeEach(() => {
    useOnDemandConfirmationStore.setState({
      currentInterrupt: sampleInterrupt,
      selectedOptionId: 'B',
      customInput: '',
      isModalOpen: true,
      historyDecisions: [],
    });
  });

  it('当 isModalOpen 为 false 时不渲染任何对话框', () => {
    useOnDemandConfirmationStore.setState({ isModalOpen: false });
    const { container } = render(<OnDemandDecisionModal />);

    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('on-demand-decision-modal')).not.toBeInTheDocument();
  });

  it('当 isModalOpen 为 true 时完整渲染决策卡片弹窗与所有选项', () => {
    render(<OnDemandDecisionModal />);

    expect(screen.getByTestId('on-demand-decision-modal')).toBeInTheDocument();
    expect(screen.getByText('按需决策确认')).toBeInTheDocument();
    expect(screen.getByText('任务 #task-999')).toBeInTheDocument();
    expect(screen.getByText('确认小红书笔记发布渠道与样式')).toBeInTheDocument();
    expect(screen.getByText(/适合多图细节展示/)).toBeInTheDocument();
    expect(screen.getByText(/适合故事性长文本/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/若以上选项不完全符合/)).toBeInTheDocument();
  });

  it('支持键盘数字键 1-3 切换选项并按 Enter 提交决策', () => {
    const handleResume = vi.fn();
    render(<OnDemandDecisionModal onResumeInterrupt={handleResume} />);

    // 按数字键 1 切换到选项 A
    fireEvent.keyDown(window, { key: '1' });
    expect(useOnDemandConfirmationStore.getState().selectedOptionId).toBe('A');

    // 按 Enter 键提交
    fireEvent.keyDown(window, { key: 'Enter' });

    expect(handleResume).toHaveBeenCalledTimes(1);
    const passedDecision = handleResume.mock.calls[0][0];
    expect(passedDecision.selectedOptionId).toBe('A');
    expect(passedDecision.selectedOptionLabel).toBe('图文轮播模板 A');
    expect(useOnDemandConfirmationStore.getState().isModalOpen).toBe(false);
  });

  it('支持补充自定义需求并随结果一同提交', () => {
    const handleResume = vi.fn();
    render(<OnDemandDecisionModal onResumeInterrupt={handleResume} />);

    const textarea = screen.getByPlaceholderText(/若以上选项不完全符合/);
    fireEvent.change(textarea, { target: { value: '封面标题加粗红色' } });

    const submitBtn = screen.getByRole('button', { name: /确认并继续/ });
    fireEvent.click(submitBtn);

    expect(handleResume).toHaveBeenCalledTimes(1);
    const passedDecision = handleResume.mock.calls[0][0];
    expect(passedDecision.customInput).toBe('封面标题加粗红色');
  });

  it('点击关闭按钮或暂缓决策按钮关闭弹窗', () => {
    render(<OnDemandDecisionModal />);

    const closeBtn = screen.getByRole('button', { name: '暂缓决策' });
    fireEvent.click(closeBtn);

    expect(useOnDemandConfirmationStore.getState().isModalOpen).toBe(false);
  });
});
