import { act, renderHook } from '@testing-library/react';
import type { KeyboardEvent } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { usePortalGestures } from '../usePortalGestures';

function keyEvent(key: string) {
  const preventDefault = vi.fn();
  return { event: { key, preventDefault } as unknown as KeyboardEvent, preventDefault };
}

function setup(panelWidth: number) {
  const onSetPanelWidth = vi.fn();
  const { result } = renderHook(() =>
    usePortalGestures({ isMobile: false, panelWidth, onClose: vi.fn(), onSetPanelWidth }),
  );
  return { result, onSetPanelWidth };
}

describe('usePortalGestures width separator', () => {
  it('exposes a focusable vertical separator with the current width and its limits', () => {
    const { result } = setup(640);

    expect(result.current.separatorProps).toMatchObject({
      role: 'separator',
      tabIndex: 0,
      'aria-orientation': 'vertical',
      'aria-valuenow': 640,
      'aria-valuemin': 320,
      'aria-valuemax': 1200,
    });
  });

  it('widens on ArrowLeft and narrows on ArrowRight because the panel docks to the right', () => {
    const { result, onSetPanelWidth } = setup(640);

    const left = keyEvent('ArrowLeft');
    act(() => result.current.separatorProps.onKeyDown(left.event));
    const right = keyEvent('ArrowRight');
    act(() => result.current.separatorProps.onKeyDown(right.event));

    expect(onSetPanelWidth).toHaveBeenNthCalledWith(1, 660);
    expect(onSetPanelWidth).toHaveBeenNthCalledWith(2, 620);
    expect(left.preventDefault).toHaveBeenCalled();
    expect(right.preventDefault).toHaveBeenCalled();
  });

  it('jumps to the limits on Home and End and never leaves them', () => {
    const { result, onSetPanelWidth } = setup(1195);

    act(() => result.current.separatorProps.onKeyDown(keyEvent('ArrowLeft').event));
    act(() => result.current.separatorProps.onKeyDown(keyEvent('Home').event));
    act(() => result.current.separatorProps.onKeyDown(keyEvent('End').event));

    expect(onSetPanelWidth).toHaveBeenNthCalledWith(1, 1200);
    expect(onSetPanelWidth).toHaveBeenNthCalledWith(2, 320);
    expect(onSetPanelWidth).toHaveBeenNthCalledWith(3, 1200);
  });

  it('ignores other keys and leaves their default behaviour alone', () => {
    const { result, onSetPanelWidth } = setup(640);

    const tab = keyEvent('Tab');
    act(() => result.current.separatorProps.onKeyDown(tab.event));

    expect(onSetPanelWidth).not.toHaveBeenCalled();
    expect(tab.preventDefault).not.toHaveBeenCalled();
  });
});
