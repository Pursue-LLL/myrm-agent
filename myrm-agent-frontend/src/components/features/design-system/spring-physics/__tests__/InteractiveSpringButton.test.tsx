import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InteractiveSpringButton } from '../InteractiveSpringButton';

describe('InteractiveSpringButton', () => {
  it('renders button with label and responds to click', () => {
    const handleClick = vi.fn();
    render(
      <InteractiveSpringButton onClick={handleClick}>
        点击测试
      </InteractiveSpringButton>
    );

    const button = screen.getByRole('button', { name: '点击测试' });
    expect(button).toBeInTheDocument();

    fireEvent.click(button);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('renders different variants and sizes', () => {
    const { rerender } = render(
      <InteractiveSpringButton variant="secondary" size="sm">
        次级小号
      </InteractiveSpringButton>
    );
    expect(screen.getByRole('button', { name: '次级小号' })).toHaveClass('bg-secondary');

    rerender(
      <InteractiveSpringButton variant="outline" size="lg">
        边框大号
      </InteractiveSpringButton>
    );
    expect(screen.getByRole('button', { name: '边框大号' })).toHaveClass('border-border/80');
  });

  it('applies spring scale transform on mouse down and recovers on mouse up', () => {
    render(
      <InteractiveSpringButton personality="energetic">
        物理按压
      </InteractiveSpringButton>
    );

    const button = screen.getByRole('button', { name: '物理按压' });
    const initialTransform = button.style.transform;

    // 按下时触发 activeScale 缩放
    fireEvent.mouseDown(button);
    const pressedTransform = button.style.transform;
    expect(pressedTransform).toContain('scale');

    // 释放后恢复
    fireEvent.mouseUp(button);
    const releasedTransform = button.style.transform;
    expect(releasedTransform).not.toBe(pressedTransform);
  });

  it('disables interactions and applies opacity when disabled', () => {
    const handleClick = vi.fn();
    render(
      <InteractiveSpringButton disabled onClick={handleClick}>
        不可用按钮
      </InteractiveSpringButton>
    );

    const button = screen.getByRole('button', { name: '不可用按钮' });
    expect(button).toBeDisabled();

    fireEvent.click(button);
    expect(handleClick).not.toHaveBeenCalled();
    expect(button.style.opacity).toBe('0.45');
  });
});
