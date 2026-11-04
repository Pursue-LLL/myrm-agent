'use client';

/**
 * [INPUT]
 * - A horizontally scrollable element (hidden scrollbar) that carries the `.scroll-fade-x` utility from globals.css.
 *
 * [OUTPUT]
 * - observeScrollEdges: keeps `data-fade-start` / `data-fade-end` in sync with the content clipped past each edge.
 * - useScrollEdgeFade: callback ref that applies observeScrollEdges while the element is mounted.
 *
 * [POS]
 * A scroller without a visible scrollbar gives no hint that controls sit out of view. The attributes let CSS fade
 * exactly the clipped edges, so a strip that fits shows no fade and a clipped one never ends mid-control.
 */

import { useCallback, useRef } from 'react';

const EDGE_TOLERANCE_PX = 1;

function setFlag(element: HTMLElement, name: 'fadeStart' | 'fadeEnd', value: boolean): void {
  const next = String(value);
  if (element.dataset[name] !== next) {
    element.dataset[name] = next;
  }
}

/** Starts tracking the element's scroll edges and returns the function that stops it. */
export function observeScrollEdges(element: HTMLElement): () => void {
  const update = () => {
    const { scrollLeft, scrollWidth, clientWidth } = element;
    setFlag(element, 'fadeStart', scrollLeft > EDGE_TOLERANCE_PX);
    setFlag(element, 'fadeEnd', scrollLeft + clientWidth < scrollWidth - EDGE_TOLERANCE_PX);
  };

  // Children resize the scrollable width without resizing the element itself, so each one is observed too.
  const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update);
  const observeLayout = () => {
    if (resizeObserver) {
      resizeObserver.disconnect();
      resizeObserver.observe(element);
      for (const child of Array.from(element.children)) {
        resizeObserver.observe(child);
      }
    }
    update();
  };

  const childListObserver = new MutationObserver(observeLayout);
  childListObserver.observe(element, { childList: true });
  element.addEventListener('scroll', update, { passive: true });
  observeLayout();

  return () => {
    element.removeEventListener('scroll', update);
    childListObserver.disconnect();
    resizeObserver?.disconnect();
  };
}

/** Callback ref: fades the edges of a horizontally scrollable element that hide content. */
export function useScrollEdgeFade<T extends HTMLElement>(): (element: T | null) => void {
  const stopObserving = useRef<(() => void) | null>(null);

  return useCallback((element: T | null) => {
    stopObserving.current?.();
    stopObserving.current = element ? observeScrollEdges(element) : null;
  }, []);
}
