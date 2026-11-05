'use client';

/**
 * [INPUT]
 * - A `[data-composer-dock]` element that is a direct child of the message column.
 *
 * [OUTPUT]
 * - ComposerClearanceSpacer: the filler at the end of the message list, as tall as the fixed composer plus a margin.
 *
 * [POS]
 * The composer floats over the page's bottom edge, so the list ends in a filler that keeps the last message
 * clear of it. The composer's height is not constant (options region, queued messages, attachments, a long draft),
 * so the filler follows it. The height is written straight to the element: a change in the composer's size must
 * not re-render a long conversation. `className` carries the minimum height.
 */

import { useEffect, useRef, type RefObject } from 'react';

const COMPOSER_MARGIN_PX = 16;

interface ComposerClearanceSpacerProps {
  /** The message column that contains both this filler and the composer dock. */
  columnRef: RefObject<HTMLElement | null>;
  className: string;
}

export function ComposerClearanceSpacer({ columnRef, className }: ComposerClearanceSpacerProps) {
  const spacerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const spacer = spacerRef.current;
    const dock = columnRef.current?.querySelector<HTMLElement>(':scope > [data-composer-dock]');
    if (!spacer || !dock) {
      return;
    }
    // The dock is `position: fixed` above a safe-area offset; both are covered by the list's end.
    const syncHeight = () => {
      const bottomOffset = Number.parseFloat(getComputedStyle(dock).bottom) || 0;
      spacer.style.height = `${Math.ceil(dock.offsetHeight + bottomOffset + COMPOSER_MARGIN_PX)}px`;
    };
    const observer = new ResizeObserver(syncHeight);
    observer.observe(dock);
    syncHeight();
    return () => observer.disconnect();
  }, [columnRef]);

  return <div ref={spacerRef} className={className} />;
}
