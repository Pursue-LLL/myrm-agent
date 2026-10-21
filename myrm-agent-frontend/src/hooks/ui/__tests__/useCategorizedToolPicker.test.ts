/** @vitest-environment jsdom */
import { renderHook, act } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { useCategorizedToolPicker } from '../useCategorizedToolPicker';

describe('useCategorizedToolPicker hook', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('initializes with default tools and default pinned list', () => {
    const { result } = renderHook(() => useCategorizedToolPicker());

    expect(result.current.tools.length).toBeGreaterThan(0);
    expect(result.current.pinnedIds).toContain('computer_control');
    expect(result.current.pinnedIds).toContain('browser_playwright');
    expect(result.current.activeCategory).toBe('all');
    expect(result.current.searchQuery).toBe('');
  });

  it('filters tools by active category', () => {
    const { result } = renderHook(() => useCategorizedToolPicker());

    act(() => {
      result.current.setActiveCategory('browser');
    });

    expect(result.current.activeCategory).toBe('browser');
    const allBrowser = result.current.filteredTools.every(
      (t) => t.category === 'browser',
    );
    expect(allBrowser).toBe(true);
    expect(result.current.filteredTools.length).toBeGreaterThan(0);
  });

  it('filters tools by query including pinyin tokens', () => {
    const { result } = renderHook(() => useCategorizedToolPicker());

    // Search by pinyin token 'dnkz'
    act(() => {
      result.current.setSearchQuery('dnkz');
    });
    expect(result.current.filteredTools.length).toBe(1);
    expect(result.current.filteredTools[0].id).toBe('computer_control');

    // Search by display name '终端'
    act(() => {
      result.current.setSearchQuery('终端');
    });
    expect(result.current.filteredTools.length).toBe(1);
    expect(result.current.filteredTools[0].id).toBe('bash_terminal');
  });

  it('toggles tool pin status and updates pinnedTools', () => {
    const { result } = renderHook(() => useCategorizedToolPicker());

    // Unpin computer_control
    act(() => {
      result.current.togglePin('computer_control');
    });
    expect(result.current.pinnedIds).not.toContain('computer_control');
    expect(
      result.current.pinnedTools.some((t) => t.id === 'computer_control'),
    ).toBe(false);

    // Pin python_data_interpreter
    act(() => {
      result.current.togglePin('python_data_interpreter');
    });
    expect(result.current.pinnedIds).toContain('python_data_interpreter');
    expect(
      result.current.pinnedTools.some((t) => t.id === 'python_data_interpreter'),
    ).toBe(true);
  });

  it('records recent tools up to 5 items', () => {
    const { result } = renderHook(() => useCategorizedToolPicker());

    act(() => {
      result.current.recordRecent('computer_control');
      result.current.recordRecent('bash_terminal');
      result.current.recordRecent('browser_playwright');
    });

    expect(result.current.recentIds[0]).toBe('browser_playwright');
    expect(result.current.recentTools.length).toBe(3);

    // Repeating an item moves it to the head
    act(() => {
      result.current.recordRecent('computer_control');
    });
    expect(result.current.recentIds[0]).toBe('computer_control');
  });

  it('toggles tool enabled state', () => {
    const { result } = renderHook(() => useCategorizedToolPicker());

    const initialEnabled = result.current.tools.find(
      (t) => t.id === 'computer_control',
    )?.enabled;

    act(() => {
      result.current.toggleToolEnabled('computer_control');
    });

    const updated = result.current.tools.find(
      (t) => t.id === 'computer_control',
    )?.enabled;
    expect(updated).toBe(!initialEnabled);
  });
});
