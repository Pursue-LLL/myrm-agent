import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { KeyboardEvent, PointerEvent } from 'react';
import { usePanelResize } from '../usePanelResize';

const OPTIONS = { storageKey: 'test-panel-width', minWidth: 300, maxWidth: 700, defaultWidth: 400 };

const keyEvent = (key: string) => ({ key, preventDefault: () => undefined }) as unknown as KeyboardEvent;
const pointerDown = (clientX: number) => ({ clientX, preventDefault: () => undefined }) as unknown as PointerEvent;
const pointerMove = (clientX: number) => {
  const event = new Event('pointermove');
  Object.defineProperty(event, 'clientX', { value: clientX });
  window.dispatchEvent(event);
};

describe('usePanelResize', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('restores a persisted width and ignores out-of-range values', () => {
    localStorage.setItem(OPTIONS.storageKey, '550');
    expect(renderHook(() => usePanelResize(OPTIONS)).result.current.panelWidth).toBe(550);

    localStorage.setItem(OPTIONS.storageKey, '5000');
    expect(renderHook(() => usePanelResize(OPTIONS)).result.current.panelWidth).toBe(400);
  });

  it('exposes complete splitter semantics for assistive technology', () => {
    const { separatorProps } = renderHook(() => usePanelResize(OPTIONS)).result.current;
    expect(separatorProps).toMatchObject({
      role: 'separator',
      tabIndex: 0,
      'aria-orientation': 'vertical',
      'aria-valuenow': 400,
      'aria-valuemin': 300,
      'aria-valuemax': 700,
    });
  });

  it('adjusts with arrow keys, jumps with Home/End, clamps and persists', () => {
    const { result } = renderHook(() => usePanelResize(OPTIONS));
    const press = (key: string) => act(() => result.current.separatorProps.onKeyDown(keyEvent(key)));

    press('ArrowLeft');
    expect(result.current.panelWidth).toBe(420);
    press('ArrowRight');
    press('ArrowRight');
    expect(result.current.panelWidth).toBe(380);
    press('End');
    expect(result.current.panelWidth).toBe(700);
    press('ArrowLeft');
    expect(result.current.panelWidth).toBe(700);
    press('Home');
    expect(result.current.panelWidth).toBe(300);
    expect(localStorage.getItem(OPTIONS.storageKey)).toBe('300');
  });

  it('ignores unrelated keys', () => {
    const { result } = renderHook(() => usePanelResize(OPTIONS));
    act(() => result.current.separatorProps.onKeyDown(keyEvent('a')));
    expect(result.current.panelWidth).toBe(400);
    expect(localStorage.getItem(OPTIONS.storageKey)).toBeNull();
  });

  it('resizes while dragging, clamps to limits and persists on release', () => {
    const { result } = renderHook(() => usePanelResize(OPTIONS));
    act(() => result.current.separatorProps.onPointerDown(pointerDown(800)));
    expect(result.current.isResizing).toBe(true);

    act(() => pointerMove(700));
    expect(result.current.panelWidth).toBe(500);
    act(() => pointerMove(0));
    expect(result.current.panelWidth).toBe(700);

    act(() => {
      window.dispatchEvent(new Event('pointerup'));
    });
    expect(result.current.isResizing).toBe(false);
    expect(localStorage.getItem(OPTIONS.storageKey)).toBe('700');

    act(() => pointerMove(900));
    expect(result.current.panelWidth).toBe(700);
  });

  it('removes window listeners when unmounted mid-drag', () => {
    const { result, unmount } = renderHook(() => usePanelResize(OPTIONS));
    act(() => result.current.separatorProps.onPointerDown(pointerDown(800)));
    unmount();
    expect(() => pointerMove(100)).not.toThrow();
  });
});
