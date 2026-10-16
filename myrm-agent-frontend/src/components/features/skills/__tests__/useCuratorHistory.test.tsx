/** @vitest-environment jsdom */

import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCuratorHistory } from '../useCuratorHistory';
import type { CuratorHistoryEntry } from '@/services/skill';

const getCuratorHistoryMock = vi.hoisted(() => vi.fn());

vi.mock('@/services/skill', () => ({ getCuratorHistory: getCuratorHistoryMock }));

const entry: CuratorHistoryEntry = {
  timestamp: '2026-10-16T04:52:33Z',
  trigger: 'background',
  skills_scanned: 41,
  total_transitions: 0,
  stale_count: 0,
  archived_count: 0,
  transitions: [],
};

describe('useCuratorHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getCuratorHistoryMock.mockResolvedValue([entry]);
  });

  it('stays closed and unfetched until the section is opened', () => {
    const { result } = renderHook(() => useCuratorHistory());

    expect(result.current.sectionProps).toMatchObject({ open: false, loading: false, entries: [] });
    expect(getCuratorHistoryMock).not.toHaveBeenCalled();
  });

  it('fetches the latest ten runs on the first open and reuses them on later opens', async () => {
    const { result } = renderHook(() => useCuratorHistory());

    await act(async () => result.current.sectionProps.onToggle());
    expect(getCuratorHistoryMock).toHaveBeenCalledWith(10);
    expect(result.current.sectionProps).toMatchObject({ open: true, loading: false, entries: [entry] });

    await act(async () => result.current.sectionProps.onToggle());
    await act(async () => result.current.sectionProps.onToggle());
    expect(result.current.sectionProps.open).toBe(true);
    expect(getCuratorHistoryMock).toHaveBeenCalledTimes(1);
  });

  it('refreshes after a new run only while the section is open', async () => {
    const { result } = renderHook(() => useCuratorHistory());

    await act(async () => result.current.reloadIfOpen());
    expect(getCuratorHistoryMock).not.toHaveBeenCalled();

    await act(async () => result.current.sectionProps.onToggle());
    await act(async () => result.current.reloadIfOpen());
    expect(getCuratorHistoryMock).toHaveBeenCalledTimes(2);
  });

  it('shows an empty history when the request fails', async () => {
    getCuratorHistoryMock.mockRejectedValue(new Error('down'));
    const { result } = renderHook(() => useCuratorHistory());

    await act(async () => result.current.sectionProps.onToggle());

    expect(result.current.sectionProps).toMatchObject({ open: true, loading: false, entries: [] });
  });
});
