/** @vitest-environment jsdom */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { WikiEditorToolbar } from '../WikiEditorToolbar';

describe('WikiEditorToolbar', () => {
  it('should render all standard toolbar buttons including Wiki双链', () => {
    const handleAction = vi.fn();
    render(<WikiEditorToolbar onAction={handleAction} />);

    expect(screen.getByRole('button', { name: 'bold' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'italic' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'h2' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'code' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'quote' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'bullet' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'todo' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'wikilink' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'table' })).toBeDefined();
  });

  it('should trigger onAction with correct payload when clicking buttons', () => {
    const handleAction = vi.fn();
    render(<WikiEditorToolbar onAction={handleAction} />);

    const boldBtn = screen.getByRole('button', { name: 'bold' });
    fireEvent.click(boldBtn);
    expect(handleAction).toHaveBeenCalledWith('bold');

    const wikilinkBtn = screen.getByRole('button', { name: 'wikilink' });
    fireEvent.click(wikilinkBtn);
    expect(handleAction).toHaveBeenCalledWith('wikilink');
  });

  it('should respect disabled prop', () => {
    const handleAction = vi.fn();
    render(<WikiEditorToolbar onAction={handleAction} disabled={true} />);

    const boldBtn = screen.getByRole('button', { name: 'bold' });
    expect(boldBtn).toBeDisabled();
    fireEvent.click(boldBtn);
    expect(handleAction).not.toHaveBeenCalled();
  });
});
