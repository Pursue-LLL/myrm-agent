import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { OmniReferenceMenu } from '../OmniReferenceMenu';
import { useOmniReferenceStore } from '../useOmniReferenceStore';
import type { OmniReferenceItem } from '../omniReferenceTypes';

describe('OmniReferenceMenu', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useOmniReferenceStore.setState({
      isOpen: false,
      searchQuery: '',
      selectedDimension: 'all',
      selectedIndex: 0,
      items: [],
      isLoading: false,
      error: null,
    });
  });

  const mockItems: OmniReferenceItem[] = [
    {
      dimension: 'session',
      target_id: 'sess_123',
      label: '数据库压测会话',
      detail: '3 天前 · 42 轮对话',
    },
    {
      dimension: 'artifact',
      target_id: 'art_456',
      label: '架构设计图',
      detail: 'SVG / Mermaid',
    },
  ];

  it('renders nothing when closed', () => {
    const { container } = render(<OmniReferenceMenu onSelectItem={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders suggestion items and handles click selection', () => {
    const mockSelect = vi.fn();
    useOmniReferenceStore.setState({
      isOpen: true,
      items: mockItems,
      selectedIndex: 0,
    });

    render(<OmniReferenceMenu onSelectItem={mockSelect} />);

    expect(screen.getByTestId('omni-reference-menu')).toBeInTheDocument();
    expect(screen.getByText('数据库压测会话')).toBeInTheDocument();
    expect(screen.getByText('架构设计图')).toBeInTheDocument();

    const item = screen.getByTestId('omni-item-session-sess_123');
    fireEvent.click(item);

    expect(mockSelect).toHaveBeenCalledWith(mockItems[0]);
    expect(useOmniReferenceStore.getState().isOpen).toBe(false);
  });

  it('handles keyboard navigation with arrow keys and Enter key', () => {
    const mockSelect = vi.fn();
    useOmniReferenceStore.setState({
      isOpen: true,
      items: mockItems,
      selectedIndex: 0,
    });

    render(<OmniReferenceMenu onSelectItem={mockSelect} />);

    // Press ArrowDown
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    expect(useOmniReferenceStore.getState().selectedIndex).toBe(1);

    // Press Enter to confirm second item
    fireEvent.keyDown(window, { key: 'Enter' });
    expect(mockSelect).toHaveBeenCalledWith(mockItems[1]);
    expect(useOmniReferenceStore.getState().isOpen).toBe(false);
  });
});
