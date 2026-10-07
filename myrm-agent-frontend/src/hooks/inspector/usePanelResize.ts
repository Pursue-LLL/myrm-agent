import { useCallback, useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent } from 'react';

const KEYBOARD_STEP = 20;

interface UsePanelResizeOptions {
  /** localStorage key used to persist the width across sessions. */
  storageKey: string;
  minWidth: number;
  maxWidth: number;
  defaultWidth: number;
}

interface SeparatorProps {
  role: 'separator';
  tabIndex: 0;
  'aria-orientation': 'vertical';
  'aria-valuenow': number;
  'aria-valuemin': number;
  'aria-valuemax': number;
  onPointerDown: (event: PointerEvent) => void;
  onKeyDown: (event: KeyboardEvent) => void;
}

/**
 * Width state for a right-docked, drag-resizable panel (Browser / Desktop / Device inspectors).
 * The left-edge separator is operable by pointer and keyboard (WAI-ARIA window splitter:
 * Left/Right adjust, Home/End jump to the limits); callers add their own `aria-label` and styling.
 */
export function usePanelResize({ storageKey, minWidth, maxWidth, defaultWidth }: UsePanelResizeOptions) {
  const [panelWidth, setPanelWidth] = useState(defaultWidth);
  const [isResizing, setIsResizing] = useState(false);
  const widthRef = useRef(panelWidth);
  widthRef.current = panelWidth;
  const stopDragRef = useRef<(() => void) | null>(null);

  const clamp = useCallback((width: number) => Math.min(maxWidth, Math.max(minWidth, width)), [minWidth, maxWidth]);

  useEffect(() => {
    const parsed = parseInt(localStorage.getItem(storageKey) ?? '', 10);
    if (parsed >= minWidth && parsed <= maxWidth) {
      setPanelWidth(parsed);
    }
  }, [storageKey, minWidth, maxWidth]);

  // A drag in flight must not leave window listeners behind if the panel unmounts.
  useEffect(() => () => stopDragRef.current?.(), []);

  const persist = useCallback(() => {
    localStorage.setItem(storageKey, String(widthRef.current));
  }, [storageKey]);

  const onPointerDown = useCallback(
    (event: PointerEvent) => {
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = widthRef.current;
      setIsResizing(true);

      const onMove = (moveEvent: globalThis.PointerEvent) => {
        setPanelWidth(clamp(startWidth + startX - moveEvent.clientX));
      };
      const stop = () => {
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onUp);
        window.removeEventListener('pointercancel', onUp);
        stopDragRef.current = null;
      };
      const onUp = () => {
        stop();
        setIsResizing(false);
        persist();
      };

      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
      window.addEventListener('pointercancel', onUp);
      stopDragRef.current = stop;
    },
    [clamp, persist],
  );

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      let target: number;
      switch (event.key) {
        case 'ArrowLeft':
          target = widthRef.current + KEYBOARD_STEP;
          break;
        case 'ArrowRight':
          target = widthRef.current - KEYBOARD_STEP;
          break;
        case 'Home':
          target = minWidth;
          break;
        case 'End':
          target = maxWidth;
          break;
        default:
          return;
      }
      event.preventDefault();
      const next = clamp(target);
      widthRef.current = next;
      setPanelWidth(next);
      persist();
    },
    [clamp, persist, minWidth, maxWidth],
  );

  const separatorProps: SeparatorProps = {
    role: 'separator',
    tabIndex: 0,
    'aria-orientation': 'vertical',
    'aria-valuenow': panelWidth,
    'aria-valuemin': minWidth,
    'aria-valuemax': maxWidth,
    onPointerDown,
    onKeyDown,
  };

  return { panelWidth, isResizing, separatorProps };
}
