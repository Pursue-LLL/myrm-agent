/**
 * Workspace file browser hook (Local Web / Tauri / Cloud agent vault)
 *
 * [INPUT]
 * - @/services/chat::browseWorkspaceFiles (POS: Workspace browse API)
 * - @/services/chat::registerWorkspaceWatch (POS: Server vault watch registration)
 * - @/hooks/useGlobalEvents (POS: Global SSE; data channel independent of notification toasts)
 *
 * [OUTPUT]
 * - useWorkspaceFiles: Hook providing file tree data via HTTP API
 *
 * [POS]
 * Data source hook for WorkspaceFileBrowser. Fetches the file tree from
 * the server browse API and auto-refreshes on WORKSPACE_FILE_CHANGED SSE.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  browseWorkspaceFiles,
  registerWorkspaceWatch,
  unregisterWorkspaceWatch,
  type FileEntry,
} from '@/services/chat';

export interface UseWorkspaceFilesReturn {
  files: FileEntry[];
  loading: boolean;
  error: string | null;
  truncated: boolean;
  refresh: () => Promise<void>;
}

export function useWorkspaceFiles(
  workspacePath: string | null | undefined,
  enabled: boolean = true,
): UseWorkspaceFilesReturn {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [truncated, setTruncated] = useState(false);
  const abortRef = useRef(false);
  const watchTargetRef = useRef('');

  const refresh = useCallback(async () => {
    if (!workspacePath || !enabled) return;

    abortRef.current = false;
    setLoading(true);
    setError(null);

    try {
      const result = await browseWorkspaceFiles(workspacePath, 2);
      if (abortRef.current) return;
      setFiles(result.entries);
      setTruncated(result.truncated);
    } catch (err) {
      if (abortRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load files');
    } finally {
      if (!abortRef.current) setLoading(false);
    }
  }, [workspacePath, enabled]);

  useEffect(() => {
    if (workspacePath && enabled) {
      refresh();
    } else {
      setFiles([]);
      setTruncated(false);
    }
    return () => {
      abortRef.current = true;
    };
  }, [workspacePath, enabled, refresh]);

  useEffect(() => {
    if (!workspacePath || !enabled) return;

    let cancelled = false;
    watchTargetRef.current = workspacePath;
    void registerWorkspaceWatch(workspacePath)
      .then((res) => {
        watchTargetRef.current = res.workspace;
      })
      .catch(() => {});

    let debounceTimer: ReturnType<typeof setTimeout> | null = null;
    const onChanged = (event: Event) => {
      const detail = (event as CustomEvent<{ workspace_path?: string }>).detail;
      const changedPath = detail?.workspace_path;
      if (!changedPath || changedPath !== watchTargetRef.current) return;
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        if (!cancelled) void refresh();
      }, 500);
    };

    window.addEventListener('workspace-file-changed', onChanged);
    return () => {
      cancelled = true;
      if (debounceTimer) clearTimeout(debounceTimer);
      window.removeEventListener('workspace-file-changed', onChanged);
      void unregisterWorkspaceWatch(workspacePath).catch(() => {});
    };
  }, [workspacePath, enabled, refresh]);

  return { files, loading, error, truncated, refresh };
}
