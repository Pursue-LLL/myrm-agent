/** @vitest-environment jsdom */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { WikiEditorToolbar } from '../WikiEditorToolbar';

describe('WikiEditorToolbar', () => {
  it('should render all standard toolbar buttons including Wiki双链', () => {
    const handleAction = vi.fn();
    render(<WikiEditorToolbar onAction={handleAction} />);

    expect(screen.getByRole('button', { name: /加粗/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /斜体/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /二级标题/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /代码块/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /引用/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /无序列表/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /待办任务/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /Wiki 双链/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /插入表格/ })).toBeDefined();
  });

  it('should trigger onAction with correct payload when clicking buttons', () => {
    const handleAction = vi.fn();
    render(<WikiEditorToolbar onAction={handleAction} />);

    const boldBtn = screen.getByRole('button', { name: /加粗/ });
    fireEvent.click(boldBtn);
    expect(handleAction).toHaveBeenCalledWith('bold');

    const wikilinkBtn = screen.getByRole('button', { name: /Wiki 双链/ });
    fireEvent.click(wikilinkBtn);
    expect(handleAction).toHaveBeenCalledWith('wikilink');
  });

  it('should respect disabled prop', () => {
    const handleAction = vi.fn();
    render(<WikiEditorToolbar onAction={handleAction} disabled={true} />);

    const boldBtn = screen.getByRole('button', { name: /加粗/ });
    expect(boldBtn).toBeDisabled();
    fireEvent.click(boldBtn);
    expect(handleAction).not.toHaveBeenCalled();
  });
});
