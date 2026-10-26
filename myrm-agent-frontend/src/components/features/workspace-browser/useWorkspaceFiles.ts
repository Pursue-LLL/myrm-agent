/**
 * Workspace file browser hook (Local Web / Tauri / Cloud agent vault)
 *
 * [INPUT]
 * - @/services/chat::browseWorkspaceFiles (POS: Workspace browse API)
 * - @/services/chat::registerWorkspaceWatch (POS: Server vault watch registration)
 * - @/hooks/globalEvents/useGlobalEvents (POS: Global SSE; data channel independent of notification toasts)
 *
 * [OUTPUT]
 * - useWorkspaceFiles: Hook providing file tree data via HTTP API: the first BROWSE_DEPTH levels up front,
 *   deeper folders on demand through loadChildren
 *
 * [POS]
 * Data source hook for WorkspaceFileBrowser. Fetches the file tree from
 * the server browse API and auto-refreshes on WORKSPACE_FILE_CHANGED SSE.
 * A scan is capped in depth and entry count, so a folder below the scanned levels arrives when the
 * user opens it; every refresh reloads the folders opened that way, so none of them goes stale.
 * A refresh swaps the tree in place (`loading` is true meanwhile, the old tree stays); only a different
 * workspace empties it.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  browseWorkspaceFiles,
  registerWorkspaceWatch,
  unregisterWorkspaceWatch,
  type FileEntry,
  type FileTreeResult,
} from '@/services/chat';

/** Levels per scan: the folders at the last level come back with `children: null` (not scanned). */
const BROWSE_DEPTH = 2;

/** The tree of a workspace nothing has been scanned for. One shared array lets React skip the re-render of a reset. */
const NO_FILES: FileEntry[] = [];

export interface UseWorkspaceFilesReturn {
  files: FileEntry[];
  loading: boolean;
  error: string | null;
  truncated: boolean;
  refresh: () => Promise<void>;
  /** Scans the folder at `dirPath` and fills its `children`; rejects when the folder cannot be read. */
  loadChildren: (dirPath: string) => Promise<void>;
}

/** `entries` with the children of the folder at `dirPath` replaced; branches that did not change keep their identity. */
function withDirectoryChildren(entries: FileEntry[], dirPath: string, children: FileEntry[]): FileEntry[] {
  let changed = false;
  const next = entries.map((entry) => {
    if (entry.type !== 'directory') {
      return entry;
    }
    if (entry.path === dirPath) {
      changed = true;
      return { ...entry, children };
    }
    if (entry.children) {
      const nested = withDirectoryChildren(entry.children, dirPath, children);
      if (nested !== entry.children) {
        changed = true;
        return { ...entry, children: nested };
      }
    }
    return entry;
  });
  return changed ? next : entries;
}

/** The folders opened on demand, by path, with what their latest scan returned. */
type OpenedFolders = Map<string, FileTreeResult>;

/** `entries` with every opened folder filled in; parents go first so a nested folder finds its parent's children. */
function withOpenedFolders(entries: FileEntry[], opened: OpenedFolders): FileEntry[] {
  return [...opened]
    .sort(([a], [b]) => a.length - b.length)
    .reduce((tree, [dir, scan]) => withDirectoryChildren(tree, dir, scan.entries), entries);
}

/** Scans each folder again; a folder that can no longer be read is missing from the answer. */
async function scanFolders(dirs: string[]): Promise<Map<string, FileTreeResult>> {
  const outcomes = await Promise.allSettled(dirs.map((dir) => browseWorkspaceFiles(dir, BROWSE_DEPTH)));
  const scans = new Map<string, FileTreeResult>();
  outcomes.forEach((outcome, index) => {
    if (outcome.status === 'fulfilled') {
      scans.set(dirs[index], outcome.value);
    }
  });
  return scans;
}

export function useWorkspaceFiles(
  workspacePath: string | null | undefined,
  enabled: boolean = true,
): UseWorkspaceFilesReturn {
  const [files, setFiles] = useState<FileEntry[]>(NO_FILES);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [truncated, setTruncated] = useState(false);
  const watchTargetRef = useRef('');
  // Bumped when a newer scan starts or the workspace changes, so a late answer to an older scan is dropped.
  const generationRef = useRef(0);
  // A fresh map per workspace: a folder answer that finds the map replaced knows its workspace is gone.
  const openedRef = useRef<OpenedFolders>(new Map());

  const refresh = useCallback(async () => {
    if (!workspacePath || !enabled) {
      return;
    }

    const generation = ++generationRef.current;
    const opened = openedRef.current;
    const openedDirs = [...opened.keys()];
    setLoading(true);
    setError(null);

    try {
      const [result, rescanned] = await Promise.all([
        browseWorkspaceFiles(workspacePath, BROWSE_DEPTH),
        scanFolders(openedDirs),
      ]);
      if (generation !== generationRef.current) {
        return;
      }
      // Folders opened while this scan ran are already in `opened` and stay as they were loaded.
      openedDirs.forEach((dir) => {
        const scan = rescanned.get(dir);
        if (scan) {
          opened.set(dir, scan);
        } else {
          opened.delete(dir);
        }
      });
      setFiles(withOpenedFolders(result.entries, opened));
      setTruncated(result.truncated || [...opened.values()].some((scan) => scan.truncated));
    } catch (err) {
      if (generation !== generationRef.current) {
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to load files');
    } finally {
      if (generation === generationRef.current) {
        setLoading(false);
      }
    }
  }, [workspacePath, enabled]);

  const loadChildren = useCallback(async (dirPath: string) => {
    const opened = openedRef.current;
    const scan = await browseWorkspaceFiles(dirPath, BROWSE_DEPTH);
    if (opened !== openedRef.current) {
      return;
    }
    opened.set(dirPath, scan);
    setFiles((tree) => withDirectoryChildren(tree, dirPath, scan.entries));
    if (scan.truncated) {
      setTruncated(true);
    }
  }, []);

  useEffect(() => {
    // A new workspace starts from nothing: the browser keeps the tree on screen during a refresh, so the
    // previous workspace's tree must be gone before this one's first scan comes back.
    openedRef.current = new Map();
    setFiles(NO_FILES);
    setTruncated(false);
    setError(null);
    if (workspacePath && enabled) {
      void refresh();
    } else {
      // A scan cut off by the switch never reaches its own `setLoading(false)`.
      setLoading(false);
    }
    return () => {
      generationRef.current += 1;
    };
  }, [workspacePath, enabled, refresh]);

  useEffect(() => {
    if (!workspacePath || !enabled) {
      return;
    }

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
      if (!changedPath || changedPath !== watchTargetRef.current) {
        return;
      }
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      debounceTimer = setTimeout(() => {
        if (!cancelled) {
          void refresh();
        }
      }, 500);
    };

    window.addEventListener('workspace-file-changed', onChanged);
    return () => {
      cancelled = true;
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      window.removeEventListener('workspace-file-changed', onChanged);
      void unregisterWorkspaceWatch(workspacePath).catch(() => {});
    };
  }, [workspacePath, enabled, refresh]);

  return { files, loading, error, truncated, refresh, loadChildren };
}
