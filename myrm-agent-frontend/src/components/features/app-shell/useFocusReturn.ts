'use client';

/**
 * Gives focus back to whatever launched a modal that has no trigger element of its own.
 *
 * [INPUT]
 * - open: whether the modal is showing
 * - enabled: false when the modal has a trigger, which Radix already returns focus to
 *
 * [OUTPUT]
 * - useFocusReturn: the `onCloseAutoFocus` handler of the modal content
 *
 * [POS]
 * Shared by ConfirmDialog and the prompt / choice dialogs of the app dialog host. A controlled modal without a
 * trigger has nowhere to return focus to, so Radix drops it on <body> and keyboard users land at the page top.
 */

import { useCallback, useLayoutEffect, useRef } from 'react';

/**
 * The element focus should come back to: the one that was focused when the modal opened, or, when that was an item
 * of a menu (the menu closes with the selection and the item unmounts), the button that opened the menu.
 */
function focusReturnTarget(active: Element | null): HTMLElement | null {
  if (!(active instanceof HTMLElement) || active === document.body) {
    return null;
  }
  const triggerId = active.closest('[role="menu"]')?.getAttribute('aria-labelledby');
  return (triggerId ? document.getElementById(triggerId) : null) ?? active;
}

export function useFocusReturn(open: boolean, enabled = true): (event: Event) => void {
  const returnFocusRef = useRef<HTMLElement | null>(null);

  // Runs in the layout phase, before Radix's FocusScope moves focus into the modal, so the focused element is still
  // the one that started the action.
  useLayoutEffect(() => {
    if (open && enabled) {
      returnFocusRef.current = focusReturnTarget(document.activeElement);
    }
  }, [open, enabled]);

  return useCallback(
    (event: Event) => {
      const target = returnFocusRef.current;
      if (enabled && target?.isConnected) {
        event.preventDefault();
        target.focus();
      }
    },
    [enabled],
  );
}
