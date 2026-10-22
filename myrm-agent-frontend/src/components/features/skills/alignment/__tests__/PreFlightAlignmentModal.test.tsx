/** @vitest-environment jsdom */

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PreFlightAlignmentModal } from '../PreFlightAlignmentModal';
import { AlignmentSubmission } from '../alignmentTypes';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    title: '前置需求结构化对齐',
    subtitle: '确认关键设计风格与交互规格',
    planFirstTitle: '先规划再执行 (Plan Before Execute)',
    planFirstDesc: '优先输出结构化线框方案',
    customPlaceholder: '输入您的自定义设计要求...',
    confirm: '确认偏好并开始执行',
    cancel: '跳过对齐直接生成',
    previewPrompt: '生成的对齐约束提示词',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('PreFlightAlignmentModal', () => {
  it('does not render when isOpen is false', () => {
    const { container } = render(<PreFlightAlignmentModal isOpen={false} onClose={vi.fn()} onSubmit={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders modal with questions and plan toggle when isOpen is true', () => {
    render(<PreFlightAlignmentModal isOpen={true} onClose={vi.fn()} onSubmit={vi.fn()} taskTitle="量子物理微课件" />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('前置需求结构化对齐')).toBeInTheDocument();
    expect(screen.getByText('先规划再执行 (Plan Before Execute)')).toBeInTheDocument();
    expect(screen.getAllByText(/视觉配色方案/i)[0]).toBeInTheDocument();
    expect(screen.getByText('科技深蓝 (Cyber Blue)')).toBeInTheDocument();
    expect(screen.getByText('现代极简灰白 (Minimalist)')).toBeInTheDocument();
  });

  it('allows toggling options and updates compiled prompt constraint', () => {
    render(<PreFlightAlignmentModal isOpen={true} onClose={vi.fn()} onSubmit={vi.fn()} />);

    // Default contains 科技深蓝
    expect(screen.getAllByText(/科技深蓝/i)[0]).toBeInTheDocument();

    // Click on 现代极简灰白
    const minimalOption = screen.getByText('现代极简灰白 (Minimalist)');
    fireEvent.click(minimalOption);

    // Verify prompt preview contains minimal light
    const preview = screen.getByText(/前置设计偏好对齐/);
    expect(preview.textContent).toContain('现代极简灰白');
  });

  it('allows toggling plan-before-execute switch', () => {
    render(<PreFlightAlignmentModal isOpen={true} onClose={vi.fn()} onSubmit={vi.fn()} />);

    const toggle = screen.getByRole('switch');
    expect(toggle).toHaveAttribute('aria-checked', 'true');

    // Click to disable plan-before-execute
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'false');

    // Prompt preview should no longer contain 先规划再执行
    const preview = screen.getByText(/前置设计偏好对齐/);
    expect(preview.textContent).not.toContain('模式: 先规划再执行');
  });

  it('submits structured submission when confirmed', () => {
    const handleSubmit = vi.fn();
    const handleClose = vi.fn();

    render(
      <PreFlightAlignmentModal
        isOpen={true}
        onClose={handleClose}
        onSubmit={handleSubmit}
        taskTitle="化学元素互动周期表"
      />,
    );

    // Type custom note
    const customInput = screen.getByPlaceholderText(/例如：支持暗色/i);
    fireEvent.change(customInput, { target: { value: '带晶格动画' } });

    // Click confirm button
    const confirmBtn = screen.getByRole('button', { name: /确认偏好并开始执行/i });
    fireEvent.click(confirmBtn);

    expect(handleSubmit).toHaveBeenCalledTimes(1);
    const submission: AlignmentSubmission = handleSubmit.mock.calls[0][0];
    expect(submission.taskSummary).toBe('化学元素互动周期表');
    expect(submission.customNotes).toBe('带晶格动画');
    expect(submission.planBeforeExecute).toBe(true);
    expect(submission.compiledPromptConstraint).toContain('带晶格动画');
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
