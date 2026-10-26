/**
 * Escape-key dismissal of one transient layer
 *
 * [INPUT]
 * - onDismiss: Closes the layer the key was meant for
 *
 * [OUTPUT]
 * - useEscapeDismiss: While the calling layer is mounted, Escape dismisses it and goes no further
 *
 * [POS]
 * Context menus and dialogs sit inside hosts that may also close on Escape (the workbench drawer listens on
 * window). The listener is on document, which an event reaches before window, and it stops the event there,
 * so one Escape closes only the innermost layer.
 */

import { useEffect } from 'react';

export function useEscapeDismiss(onDismiss: () => void): void {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onDismiss();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onDismiss]);
}
