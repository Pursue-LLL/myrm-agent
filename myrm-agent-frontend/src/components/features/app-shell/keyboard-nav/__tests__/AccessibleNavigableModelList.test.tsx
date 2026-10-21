import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { AccessibleNavigableModelList } from '../AccessibleNavigableModelList';
import type { NavigableModelItem } from '../modelPickerKeyboardTypes';

describe('AccessibleNavigableModelList', () => {
  const mockItems: NavigableModelItem[] = [
    {
      id: 'gpt-4o',
      providerId: 'openai',
      model: 'gpt-4o',
      label: 'GPT-4o',
      badge: '128k',
      description: '多模态旗舰模型',
    },
    {
      id: 'claude-3-7',
      providerId: 'anthropic',
      model: 'claude-3-7-sonnet',
      label: 'Claude 3.7 Sonnet',
      badge: '200k',
      description: '支持自适应长思维链推演',
    },
    {
      id: 'blocked-model',
      providerId: 'restricted',
      model: 'restricted-v1',
      label: '受限内部模型',
      disabled: true,
      description: '组织安全策略拦截',
    },
  ];

  it('should render model list with items and keyboard shortcuts help bar', () => {
    render(<AccessibleNavigableModelList items={mockItems} selectedId="gpt-4o" />);

    expect(screen.getByTestId('accessible-navigable-model-list')).toBeInTheDocument();
    expect(screen.getByTestId('navigable-model-listbox')).toBeInTheDocument();
    expect(screen.getByText('GPT-4o')).toBeInTheDocument();
    expect(screen.getByText('Claude 3.7 Sonnet')).toBeInTheDocument();
    expect(screen.getByText('受限内部模型')).toBeInTheDocument();
    expect(screen.getByText(/漫游/)).toBeInTheDocument();
  });

  it('should render empty prompt when items array is empty', () => {
    render(<AccessibleNavigableModelList items={[]} />);
    expect(screen.getByText('暂无匹配的模型项')).toBeInTheDocument();
  });

  it('should support full keyboard navigation with ArrowDown and Enter selection', () => {
    const onSelect = vi.fn();
    render(<AccessibleNavigableModelList items={mockItems} onSelect={onSelect} />);

    const listbox = screen.getByTestId('navigable-model-listbox');
    // 初始高亮项为第 0 项 (gpt-4o)
    expect(listbox.getAttribute('aria-activedescendant')).toBe('model-opt-gpt-4o');

    // 按下 ArrowDown 移动到第 1 项 (claude-3-7)
    act(() => {
      fireEvent.keyDown(listbox, { key: 'ArrowDown' });
    });
    expect(listbox.getAttribute('aria-activedescendant')).toBe('model-opt-claude-3-7');

    // 按下 Enter 确认选择第 1 项
    act(() => {
      fireEvent.keyDown(listbox, { key: 'Enter' });
    });
    expect(onSelect).toHaveBeenCalledWith(mockItems[1]);
  });

  it('should trigger onClose when Escape is pressed', () => {
    const onClose = vi.fn();
    render(<AccessibleNavigableModelList items={mockItems} onClose={onClose} />);

    const listbox = screen.getByTestId('navigable-model-listbox');
    act(() => {
      fireEvent.keyDown(listbox, { key: 'Escape' });
    });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('should trigger onSelect on click but not when item is disabled', () => {
    const onSelect = vi.fn();
    render(<AccessibleNavigableModelList items={mockItems} onSelect={onSelect} />);

    // 点击可用项
    const item1 = screen.getByTestId('model-nav-item-claude-3-7');
    fireEvent.click(item1);
    expect(onSelect).toHaveBeenCalledWith(mockItems[1]);

    // 点击受限禁用项
    const disabledItem = screen.getByTestId('model-nav-item-blocked-model');
    fireEvent.click(disabledItem);
    expect(onSelect).toHaveBeenCalledTimes(1); // 次数仍为 1
  });
});
