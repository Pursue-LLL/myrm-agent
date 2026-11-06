import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useHistorySearch } from '../useHistorySearch';

describe('useHistorySearch', () => {
  const applyKeyword = vi.fn<(keyword: string) => void>();

  beforeEach(() => {
    applyKeyword.mockClear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const setup = (appliedKeyword = '') => renderHook(() => useHistorySearch(appliedKeyword, applyKeyword));
  const advance = (ms: number) => act(() => vi.advanceTimersByTime(ms));

  it('starts closed and echoes the keyword that is already applied', () => {
    const { result } = setup('needle');

    expect(result.current.showSearch).toBe(false);
    expect(result.current.localKeyword).toBe('needle');
  });

  it('echoes typing at once and applies only the last keyword after the pause', () => {
    const { result } = setup();

    act(() => result.current.handleSearchChange('a'));
    advance(200);
    act(() => result.current.handleSearchChange('ab'));
    expect(result.current.localKeyword).toBe('ab');

    advance(299);
    expect(applyKeyword).not.toHaveBeenCalled();
    advance(1);
    expect(applyKeyword.mock.calls).toEqual([['ab']]);
  });

  it('applies an empty keyword and closes when cleared', () => {
    const { result } = setup('needle');
    act(() => result.current.handleToggleSearch());
    expect(result.current.showSearch).toBe(true);

    act(() => result.current.handleClearSearch());

    expect(result.current.showSearch).toBe(false);
    expect(result.current.localKeyword).toBe('');
    expect(applyKeyword.mock.calls).toEqual([['']]);
  });

  it('never applies a keyword that was typed just before the field was cleared', () => {
    const { result } = setup();
    act(() => result.current.handleToggleSearch());

    act(() => result.current.handleSearchChange('abc'));
    act(() => result.current.handleClearSearch());
    advance(1_000);

    expect(applyKeyword.mock.calls).toEqual([['']]);
  });

  it('never applies a keyword that was typed just before the toggle closed the field', () => {
    const { result } = setup();
    act(() => result.current.handleToggleSearch());

    act(() => result.current.handleSearchChange('abc'));
    act(() => result.current.handleToggleSearch());
    advance(1_000);

    expect(result.current.showSearch).toBe(false);
    expect(applyKeyword.mock.calls).toEqual([['']]);
  });

  it('closing an empty field leaves the applied keyword alone', () => {
    const { result } = setup();
    act(() => result.current.handleToggleSearch());

    act(() => result.current.handleToggleSearch());
    advance(1_000);

    expect(result.current.showSearch).toBe(false);
    expect(applyKeyword).not.toHaveBeenCalled();
  });

  it('focuses the field on the frame after it opens', () => {
    const { result } = setup();
    const input = document.createElement('input');
    const focus = vi.spyOn(input, 'focus');
    result.current.searchInputRef.current = input;

    act(() => result.current.handleToggleSearch());
    expect(focus).not.toHaveBeenCalled();
    advance(16);

    expect(focus).toHaveBeenCalledTimes(1);
  });

  it('drops a keyword that is still waiting when the list goes away', () => {
    const { result, unmount } = setup();

    act(() => result.current.handleSearchChange('abc'));
    unmount();
    advance(1_000);

    expect(applyKeyword).not.toHaveBeenCalled();
  });
});
