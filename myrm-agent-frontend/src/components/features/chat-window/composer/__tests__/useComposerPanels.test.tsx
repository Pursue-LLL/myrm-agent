import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useComposerPanels } from '../useComposerPanels';

const OPTIONS_KEY = 'myrm.composer.optionsOpen';

function useViewport(isDesktop: boolean): void {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({ matches: isDesktop, media: query })),
  );
}

describe('useComposerPanels', () => {
  beforeEach(() => {
    localStorage.clear();
    useViewport(true);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('opens the phone action sheet and closes it again', () => {
    const { result } = renderHook(() => useComposerPanels());
    expect(result.current.isMobileSheetOpen).toBe(false);

    act(() => result.current.openMobileSheet());
    expect(result.current.isMobileSheetOpen).toBe(true);

    act(() => result.current.closeMobileSheet());
    expect(result.current.isMobileSheetOpen).toBe(false);
  });

  it('edits capabilities in the options popover on a desktop and in the action sheet on a phone', () => {
    const desktop = renderHook(() => useComposerPanels());
    act(() => desktop.result.current.openCapabilityEditor());
    expect(desktop.result.current.isTurnCapabilityOpen).toBe(true);
    expect(desktop.result.current.isMobileSheetOpen).toBe(false);

    useViewport(false);
    const phone = renderHook(() => useComposerPanels());
    act(() => phone.result.current.openCapabilityEditor());
    expect(phone.result.current.isMobileSheetOpen).toBe(true);
    expect(phone.result.current.isTurnCapabilityOpen).toBe(false);
  });

  it('shows the options region while capabilities are edited without changing the saved choice', () => {
    const { result } = renderHook(() => useComposerPanels());
    expect(result.current.optionsExpanded).toBe(false);

    act(() => result.current.openCapabilityEditor());
    expect(result.current.optionsExpanded).toBe(true);
    expect(localStorage.getItem(OPTIONS_KEY)).toBeNull();

    act(() => result.current.setIsTurnCapabilityOpen(false));
    expect(result.current.optionsExpanded).toBe(false);
  });

  it('toggles the region and remembers the choice', () => {
    const { result } = renderHook(() => useComposerPanels());

    act(() => result.current.toggleOptions());
    expect(result.current.optionsExpanded).toBe(true);
    expect(localStorage.getItem(OPTIONS_KEY)).toBe('1');

    act(() => result.current.toggleOptions());
    expect(result.current.optionsExpanded).toBe(false);
    expect(localStorage.getItem(OPTIONS_KEY)).toBe('0');
  });

  it('closes the capability popover and the region together when the toggle is pressed while it is open', () => {
    const { result } = renderHook(() => useComposerPanels());
    act(() => result.current.openCapabilityEditor());
    expect(result.current.optionsExpanded).toBe(true);

    act(() => result.current.toggleOptions());

    expect(result.current.isTurnCapabilityOpen).toBe(false);
    expect(result.current.optionsExpanded).toBe(false);
  });

  it('gives every composer region its own id', () => {
    const first = renderHook(() => useComposerPanels());
    const second = renderHook(() => useComposerPanels());

    expect(first.result.current.optionsRegionId).not.toBe(second.result.current.optionsRegionId);
  });
});
