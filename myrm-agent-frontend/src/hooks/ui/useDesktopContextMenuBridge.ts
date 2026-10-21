/**
 * Downstream Desktop Native Context Menu Bridge Hook.
 *
 * [INPUT] React, standard DOM events
 * [OUTPUT] useDesktopContextMenuBridge & dispatchDesktopContextMenu
 * [POS] src/hooks/ui/useDesktopContextMenuBridge.ts
 */

import { useCallback } from 'react';

export interface DesktopContextMenuDetail {
  sessionId: string;
  title: string;
  clientX: number;
  clientY: number;
  source: 'session_row' | 'artifact' | 'file';
  extra?: Record<string, string | number | boolean>;
}

export const DESKTOP_CONTEXT_MENU_EVENT = 'myrm:session-row-contextmenu';

/**
 * Check whether the current runtime is a desktop native wrapper (e.g. Tauri).
 */
export function isDesktopEnvironment(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  const win = window as unknown as {
    __TAURI__?: unknown;
    __TAURI_INTERNALS__?: unknown;
  };
  return Boolean(win.__TAURI__ || win.__TAURI_INTERNALS__);
}

/**
 * Programmatically dispatch desktop native context menu custom event.
 */
export function dispatchDesktopContextMenu(detail: DesktopContextMenuDetail): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  const event = new CustomEvent<DesktopContextMenuDetail>(DESKTOP_CONTEXT_MENU_EVENT, {
    bubbles: true,
    cancelable: true,
    detail,
  });
  return window.dispatchEvent(event);
}

export interface UseDesktopContextMenuBridgeOptions {
  onWebFallback?: (detail: DesktopContextMenuDetail) => void;
}

/**
 * Hook to bridge right-click context menu events to native desktop wrappers.
 */
export function useDesktopContextMenuBridge(options: UseDesktopContextMenuBridgeOptions = {}) {
  const { onWebFallback } = options;

  const handleContextMenu = useCallback(
    (e: React.MouseEvent, detail: Omit<DesktopContextMenuDetail, 'clientX' | 'clientY'>) => {
      const fullDetail: DesktopContextMenuDetail = {
        ...detail,
        clientX: e.clientX,
        clientY: e.clientY,
      };

      if (isDesktopEnvironment()) {
        e.preventDefault();
        dispatchDesktopContextMenu(fullDetail);
      } else if (onWebFallback) {
        e.preventDefault();
        onWebFallback(fullDetail);
      }
    },
    [onWebFallback],
  );

  return {
    isDesktop: isDesktopEnvironment(),
    handleContextMenu,
    dispatchContextMenu: dispatchDesktopContextMenu,
  };
}
