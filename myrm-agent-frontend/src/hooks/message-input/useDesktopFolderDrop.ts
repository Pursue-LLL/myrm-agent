/**
 * [INPUT]
 * - @/lib/tauri (isTauriEnvironment, listenTauriEvent)
 * - @/services/chat::grantSessionAccessRoot (POS: grant session directory API)
 * - @/lib/sessionAccessRefresh::refreshSessionAccessRoots (POS: FE store sync)
 * - @/store/useChatStore (chatId, sessionAccessRoots)
 *
 * [OUTPUT]
 * - useDesktopFolderDrop: Hook to handle native Tauri folder drag-and-drop grants
 * - normalizeDesktopPath: Normalizes Windows/POSIX paths to standard forward slashes
 *
 * [POS]
 * Desktop native folder drag-and-drop handler for zero-friction workspace directory grants.
 */

import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { isTauriEnvironment, listenTauriEvent } from '@/lib/tauri';
import { grantSessionAccessRoot } from '@/services/chat';
import { refreshSessionAccessRoots } from '@/lib/sessionAccessRefresh';
import useChatStore from '@/store/useChatStore';

/**
 * Normalizes Windows backslashes to forward slashes and strips trailing slashes (except root).
 */
export function normalizeDesktopPath(rawPath: string): string {
  const trimmed = rawPath.trim();
  if (!trimmed) {return '';}

  let normalized = trimmed.replace(/\\+/g, '/');
  // Collapse multiple consecutive slashes (except initial // for UNC if any)
  normalized = normalized.replace(/(?!^)\/+/g, '/');

  // Remove trailing slash unless it's the root '/' or Windows root 'C:/'
  if (normalized.length > 1 && normalized.endsWith('/') && !/^[a-zA-Z]:\/$/.test(normalized)) {
    normalized = normalized.slice(0, -1);
  }

  return normalized;
}

export interface UseDesktopFolderDropOptions {
  disabled?: boolean;
  onFolderGranted?: (path: string) => void;
}

export interface TauriDragDropPayload {
  paths?: string[];
  position?: { x: number; y: number };
}

export function useDesktopFolderDrop(options: UseDesktopFolderDropOptions = {}) {
  const { disabled = false, onFolderGranted } = options;
  const chatId = useChatStore((state) => state.chatId);
  const [isDraggingOver, setIsDraggingOver] = useState(false);

  const handleDroppedPaths = useCallback(
    async (rawPaths: string[]) => {
      if (disabled || !rawPaths.length) {return;}

      const validPaths = rawPaths
        .map(normalizeDesktopPath)
        .filter((p) => p.length > 0);

      if (!validPaths.length) {return;}

      for (const targetPath of validPaths) {
        try {
          if (chatId) {
            await grantSessionAccessRoot(chatId, targetPath, true);
            await refreshSessionAccessRoots(chatId, {
              optimistic: {
                path: targetPath,
                writable: true,
                source: 'desktop_drag_drop',
              },
            });
          }
          onFolderGranted?.(targetPath);
        } catch (error) {
          console.warn(`Failed to grant directory access for ${targetPath}:`, error);
          toast.error(`Failed to grant directory access: ${targetPath}`);
        }
      }
    },
    [chatId, disabled, onFolderGranted],
  );

  useEffect(() => {
    if (!isTauriEnvironment() || disabled) {
      return;
    }

    const unlisteners: (() => void)[] = [];

    const setupListeners = async () => {
      try {
        const unlistenDrop = await listenTauriEvent('tauri://drag-drop', (event) => {
          setIsDraggingOver(false);
          const payload = (event as { payload?: TauriDragDropPayload })?.payload ?? (event as TauriDragDropPayload);
          const paths = Array.isArray(payload?.paths) ? payload.paths : [];
          if (paths.length > 0) {
            void handleDroppedPaths(paths);
          }
        });
        unlisteners.push(unlistenDrop);

        const unlistenEnter = await listenTauriEvent('tauri://drag-enter', () => {
          setIsDraggingOver(true);
        });
        unlisteners.push(unlistenEnter);

        const unlistenLeave = await listenTauriEvent('tauri://drag-leave', () => {
          setIsDraggingOver(false);
        });
        unlisteners.push(unlistenLeave);
      } catch (error) {
        console.warn('Failed to register Tauri drag-drop listeners:', error);
      }
    };

    void setupListeners();

    return () => {
      for (const unlisten of unlisteners) {
        unlisten();
      }
    };
  }, [disabled, handleDroppedPaths]);

  return {
    isDraggingOver,
    handleDroppedPaths,
  };
}
