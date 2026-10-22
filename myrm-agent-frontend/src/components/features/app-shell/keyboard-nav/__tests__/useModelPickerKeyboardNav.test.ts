import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useModelPickerKeyboardNav } from '../useModelPickerKeyboardNav';
import type { NavigableModelItem } from '../modelPickerKeyboardTypes';

describe('useModelPickerKeyboardNav', () => {
  const mockItems: NavigableModelItem[] = [
    { id: 'm1', providerId: 'openai', model: 'gpt-4o', label: 'GPT-4o' },
    { id: 'm2', providerId: 'anthropic', model: 'claude-3-7-sonnet', label: 'Claude 3.7', disabled: true },
    { id: 'm3', providerId: 'deepseek', model: 'deepseek-v3', label: 'DeepSeek V3' },
  ];

  it('should initialize activeIndex to first enabled item when opened', () => {
    const { result } = renderHook(() =>
      useModelPickerKeyboardNav({
        items: mockItems,
        isOpen: true,
      }),
    );

    expect(result.current.activeIndex).toBe(0);
    expect(result.current.activeItem?.id).toBe('m1');
  });

  it('should reset activeIndex to -1 when closed', () => {
    const { result, rerender } = renderHook(
      ({ isOpen }) =>
        useModelPickerKeyboardNav({
          items: mockItems,
          isOpen,
        }),
      { initialProps: { isOpen: true } },
    );

    expect(result.current.activeIndex).toBe(0);

    rerender({ isOpen: false });
    expect(result.current.activeIndex).toBe(-1);
  });

  it('should navigate downwards with ArrowDown and skip disabled items', () => {
    const { result } = renderHook(() =>
      useModelPickerKeyboardNav({
        items: mockItems,
        isOpen: true,
      }),
    );

    const event = {
      key: 'ArrowDown',
      preventDefault: vi.fn(),
    } as unknown as React.KeyboardEvent;

    act(() => {
      result.current.handleKeyDown(event);
    });

    // 跳过 disabled 的 m2，直接到 m3（索引 2）
    expect(result.current.activeIndex).toBe(2);
    expect(result.current.activeItem?.id).toBe('m3');
    expect(event.preventDefault).toHaveBeenCalled();
  });

  it('should navigate upwards with ArrowUp and cycle around', () => {
    const { result } = renderHook(() =>
      useModelPickerKeyboardNav({
        items: mockItems,
        isOpen: true,
      }),
    );

    const event = {
      key: 'ArrowUp',
      preventDefault: vi.fn(),
    } as unknown as React.KeyboardEvent;

    act(() => {
      result.current.handleKeyDown(event);
    });

    // 从 0 往上循环到末尾 m3（索引 2）
    expect(result.current.activeIndex).toBe(2);
  });

  it('should trigger onSelect on Enter when current item is enabled', () => {
    const onSelect = vi.fn();
    const { result } = renderHook(() =>
      useModelPickerKeyboardNav({
        items: mockItems,
        isOpen: true,
        onSelect,
      }),
    );

    const enterEvent = {
      key: 'Enter',
      preventDefault: vi.fn(),
    } as unknown as React.KeyboardEvent;

    act(() => {
      result.current.handleKeyDown(enterEvent);
    });

    expect(onSelect).toHaveBeenCalledWith(mockItems[0]);
    expect(enterEvent.preventDefault).toHaveBeenCalled();
  });

  it('should trigger onClose on Escape', () => {
    const onClose = vi.fn();
    const { result } = renderHook(() =>
      useModelPickerKeyboardNav({
        items: mockItems,
        isOpen: true,
        onClose,
      }),
    );

    const escEvent = {
      key: 'Escape',
      preventDefault: vi.fn(),
    } as unknown as React.KeyboardEvent;

    act(() => {
      result.current.handleKeyDown(escEvent);
    });

    expect(onClose).toHaveBeenCalled();
    expect(escEvent.preventDefault).toHaveBeenCalled();
  });
});
