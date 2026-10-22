import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InlineReviewCommentBubble } from '../InlineReviewCommentBubble';

describe('InlineReviewCommentBubble', () => {
  const defaultProps = {
    filePath: 'src/lib/calculator.ts',
    lineNumber: 88,
    lineType: 'addition' as const,
    selectedCode: 'return a / b;',
    sessionId: 'sess-test',
    messageId: 'msg-test',
    onDismiss: vi.fn(),
    onSubmitFix: vi.fn(),
  };

  it('renders target filename and line number badge', () => {
    render(<InlineReviewCommentBubble {...defaultProps} />);
    expect(screen.getByText('calculator.ts')).toBeDefined();
    expect(screen.getByText('L88')).toBeDefined();
    expect(screen.getByText('return a / b;')).toBeDefined();
  });

  it('applies preset review tag when clicked', () => {
    render(<InlineReviewCommentBubble {...defaultProps} />);
    const presetBtn = screen.getByText('防御性判空处理');
    fireEvent.click(presetBtn);

    const textarea = screen.getByRole('textbox', { name: /代码审查批注内容/ }) as HTMLTextAreaElement;
    expect(textarea.value).toBe('防御性判空处理');
  });

  it('calls onDismiss when clicking close or cancel button', () => {
    const onDismiss = vi.fn();
    render(<InlineReviewCommentBubble {...defaultProps} onDismiss={onDismiss} />);

    const closeBtn = screen.getByRole('button', { name: /关闭批注气泡/ });
    fireEvent.click(closeBtn);
    expect(onDismiss).toHaveBeenCalledTimes(1);

    const cancelBtn = screen.getByRole('button', { name: /取消/ });
    fireEvent.click(cancelBtn);
    expect(onDismiss).toHaveBeenCalledTimes(2);
  });

  it('submits surgical fix with constructed prompt on click', () => {
    const onSubmitFix = vi.fn();
    render(<InlineReviewCommentBubble {...defaultProps} onSubmitFix={onSubmitFix} />);

    const textarea = screen.getByRole('textbox', { name: /代码审查批注内容/ });
    fireEvent.change(textarea, { target: { value: '必须校验 b === 0 避免除零异常' } });

    const submitBtn = screen.getByRole('button', { name: /定向修复/ });
    fireEvent.click(submitBtn);

    expect(onSubmitFix).toHaveBeenCalledTimes(1);
    const [comment, prompt] = onSubmitFix.mock.calls[0];
    expect(comment.comment).toBe('必须校验 b === 0 避免除零异常');
    expect(comment.filePath).toBe('src/lib/calculator.ts');
    expect(comment.lineNumber).toBe(88);
    expect(prompt).toContain('目标文件：src/lib/calculator.ts（第 88 行）');
    expect(prompt).toContain('必须校验 b === 0 避免除零异常');
  });
});
