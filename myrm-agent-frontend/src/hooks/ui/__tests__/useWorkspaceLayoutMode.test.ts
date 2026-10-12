import { renderHook, act } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import {
  useWorkspaceLayoutMode,
  WORKSPACE_LAYOUT_STORAGE_KEY,
  DEFAULT_LAYOUT_MODE,
} from '../useWorkspaceLayoutMode';

describe('useWorkspaceLayoutMode hook', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('initializes with default layout mode easy_minimal when storage is empty', () => {
    const { result } = renderHook(() => useWorkspaceLayoutMode());

    expect(result.current.layoutMode).toBe(DEFAULT_LAYOUT_MODE);
    expect(result.current.isEasyMinimal).toBe(true);
    expect(result.current.isCopilot).toBe(false);
  });

  it('restores valid layout mode from localStorage', () => {
    localStorage.setItem(WORKSPACE_LAYOUT_STORAGE_KEY, 'copilot');

    const { result } = renderHook(() => useWorkspaceLayoutMode());

    expect(result.current.layoutMode).toBe('copilot');
    expect(result.current.isCopilot).toBe(true);
    expect(result.current.isEasyMinimal).toBe(false);
  });

  it('updates layout mode and persists to localStorage on setLayoutMode', () => {
    const { result } = renderHook(() => useWorkspaceLayoutMode());

    act(() => {
      result.current.setLayoutMode('multi_agent');
    });

    expect(result.current.layoutMode).toBe('multi_agent');
    expect(result.current.isMultiAgent).toBe(true);
    expect(localStorage.getItem(WORKSPACE_LAYOUT_STORAGE_KEY)).toBe('multi_agent');
  });

  it('resets to default layout mode on resetLayout', () => {
    const { result } = renderHook(() => useWorkspaceLayoutMode());

    act(() => {
      result.current.setLayoutMode('remote_compute');
    });
    expect(result.current.isRemoteCompute).toBe(true);

    act(() => {
      result.current.resetLayout();
    });
    expect(result.current.layoutMode).toBe(DEFAULT_LAYOUT_MODE);
    expect(localStorage.getItem(WORKSPACE_LAYOUT_STORAGE_KEY)).toBe(DEFAULT_LAYOUT_MODE);
  });
});
