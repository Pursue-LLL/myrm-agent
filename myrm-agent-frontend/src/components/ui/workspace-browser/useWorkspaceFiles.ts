/**
 * Workspace file browser hook (Web/SaaS mode)
 *
 * [INPUT]
 * - @/services/chat::browseWorkspaceFiles (POS: Workspace browse API)
 *
 * [OUTPUT]
 * - useWorkspaceFiles: Hook providing file tree data via HTTP API
 *
 * [POS]
 * Data source hook for WorkspaceFileBrowser. Fetches the file tree from
 * the server browse API. Unlike useFileWatcher (Tauri-only), this works
 * in Web/SaaS environments via HTTP.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { browseWorkspaceFiles, type FileEntry } from '@/services/chat';

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

  return { files, loading, error, truncated, refresh };
}
