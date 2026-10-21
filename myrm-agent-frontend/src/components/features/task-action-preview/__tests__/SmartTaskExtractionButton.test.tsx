import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SmartTaskExtractionButton } from '../SmartTaskExtractionButton';
import type { CleanedActionItem } from '../taskActionPreviewTypes';

describe('SmartTaskExtractionButton', () => {
  it('renders extraction button with default label and icon', () => {
    render(<SmartTaskExtractionButton rawText="好的，建议重构此模块。您看行吗？" />);
    const btn = screen.getByTestId('smart-task-extraction-btn');
    expect(btn).toBeDefined();
    expect(btn.textContent).toContain('转为 Task');
  });

  it('triggers onExtract and dispatches custom event on click', () => {
    const onExtract = vi.fn();
    const eventListener = vi.fn();
    window.addEventListener('myrm:inject-composer-task', eventListener);

    render(
      <SmartTaskExtractionButton
        rawText="好的，建议修复会话水化器中的空指针异常。您看合适吗？"
        onExtract={onExtract}
      />,
    );

    const btn = screen.getByTestId('smart-task-extraction-btn');
    fireEvent.click(btn);

    expect(onExtract).toHaveBeenCalledTimes(1);
    const extracted: CleanedActionItem = onExtract.mock.calls[0][0];
    expect(extracted.actionableTitle).toBe('修复会话水化器中的空指针异常');
    expect(extracted.category).toBe('fix');

    expect(eventListener).toHaveBeenCalledTimes(1);
    const customEvent = eventListener.mock.calls[0][0] as CustomEvent<CleanedActionItem>;
    expect(customEvent.detail.actionableTitle).toBe('修复会话水化器中的空指针异常');

    // UI transitions into recent extracted state
    expect(btn.textContent).toContain('已转 Task');

    window.removeEventListener('myrm:inject-composer-task', eventListener);
  });

  it('disables button when rawText is empty or whitespace', () => {
    const onExtract = vi.fn();
    render(<SmartTaskExtractionButton rawText="   " onExtract={onExtract} />);
    const btn = screen.getByTestId('smart-task-extraction-btn');
    expect(btn.hasAttribute('disabled')).toBe(true);

    fireEvent.click(btn);
    expect(onExtract).not.toHaveBeenCalled();
  });

  it('renders compact mode without text label', () => {
    render(<SmartTaskExtractionButton rawText="重构目标" compact={true} />);
    const btn = screen.getByTestId('smart-task-extraction-btn');
    expect(btn.textContent).not.toContain('转为 Task');
    expect(btn.getAttribute('aria-label')).toBeDefined();
  });
});
