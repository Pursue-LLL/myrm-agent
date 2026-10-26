'use client';

/**
 * [INPUT]
 * - useChatStore from @/store/useChatStore (POS: workspaceDir of the current chat)
 * - useWorkspaceFiles, WorkspaceFileBrowser, WorkspaceFilePreview from @/components/features/workspace-browser
 *   (POS: the file tree, live refresh and preview shared with the sidebar workspace view)
 * - useTranslations from next-intl (namespace: 'workbench.files')
 *
 * [OUTPUT]
 * - filterFileEntries: Keeps the entries whose workspace-relative path matches a query
 * - WorkbenchFiles: Files tab of the auxiliary workbench — quick search over the shared workspace browser,
 *   with the file preview laid over the tree
 *
 * [POS]
 * Files tab of the auxiliary workbench. It owns no file-reading logic: the tree, uploads, rename/move/delete
 * and previews all come from the workspace browser, so the workbench and the sidebar can never disagree.
 */

import React, { useCallback, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { useTranslations } from 'next-intl';
import { FolderTree, Search } from 'lucide-react';
import { useWorkspaceFiles } from '@/components/features/workspace-browser/useWorkspaceFiles';
import type { FileEntry } from '@/services/chat';
import useChatStore from '@/store/useChatStore';

const panelLoading = (
  <div className="flex h-full items-center justify-center p-6">
    <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
  </div>
);

// The browser and the preview pull in upload, diff and rich-media code; this tab sits in a globally
// mounted drawer, so they load only once someone opens the Files tab.
const WorkspaceFileBrowser = dynamic(
  () =>
    import('@/components/features/workspace-browser/WorkspaceFileBrowser').then((module) => ({
      default: module.WorkspaceFileBrowser,
    })),
  { ssr: false, loading: () => panelLoading },
);

const WorkspaceFilePreview = dynamic(
  () =>
    import('@/components/features/workspace-browser/WorkspaceFilePreview').then((module) => ({
      default: module.WorkspaceFilePreview,
    })),
  { ssr: false, loading: () => panelLoading },
);

/**
 * Keeps entries whose workspace-relative path contains the query, plus the directories that lead to a match.
 * Matching on the relative path keeps the workspace root's own folder names from matching everything.
 */
export function filterFileEntries(entries: FileEntry[], query: string, workspacePath: string): FileEntry[] {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return entries;
  }

  const searchKey = (entry: FileEntry): string =>
    (entry.path.startsWith(workspacePath) ? entry.path.slice(workspacePath.length) : entry.name).toLowerCase();

  const keep = (list: FileEntry[]): FileEntry[] => {
    const kept: FileEntry[] = [];
    for (const entry of list) {
      if (searchKey(entry).includes(needle)) {
        kept.push(entry);
        continue;
      }
      if (entry.type === 'directory' && entry.children) {
        const children = keep(entry.children);
        if (children.length > 0) {
          kept.push({ ...entry, children });
        }
      }
    }
    return kept;
  };

  return keep(entries);
}

function CenteredHint({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-xs text-muted-foreground">
      <FolderTree className="h-8 w-8 opacity-40" />
      <span>{children}</span>
    </div>
  );
}

export function WorkbenchFiles() {
  const t = useTranslations('workbench.files');
  const workspaceDir = useChatStore((s) => s.workspaceDir);
  const { files, loading, error, truncated, refresh } = useWorkspaceFiles(workspaceDir);
  const [query, setQuery] = useState('');
  const [previewFile, setPreviewFile] = useState<FileEntry | null>(null);

  const visibleFiles = useMemo(
    () => (workspaceDir ? filterFileEntries(files, query, workspaceDir) : []),
    [files, query, workspaceDir],
  );

  const handleFileClick = useCallback((file: FileEntry) => {
    if (file.type === 'file') {
      setPreviewFile(file);
    }
  }, []);

  const handleClosePreview = useCallback(() => setPreviewFile(null), []);

  if (!workspaceDir) {
    return <CenteredHint>{t('workspaceUnavailable')}</CenteredHint>;
  }

  const hasNoMatch = query.trim() !== '' && files.length > 0 && visibleFiles.length === 0;

  return (
    <div className="relative flex h-full flex-col overflow-hidden text-foreground">
      <div className="border-b border-border/60 bg-card/60 p-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('searchPlaceholder')}
            aria-label={t('searchPlaceholder')}
            className="w-full rounded-lg border border-border/70 bg-background py-1 pl-8 pr-2.5 text-xs focus:outline-hidden focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      <div className="relative min-h-0 flex-1">
        {/* Stays mounted while a search finds nothing, so the expanded folders survive editing the query. */}
        <WorkspaceFileBrowser
          workspacePath={workspaceDir}
          files={visibleFiles}
          loading={loading}
          error={error ? t('workspaceUnavailable') : null}
          truncated={truncated}
          onRefresh={refresh}
          onFileClick={handleFileClick}
          className="h-full"
        />
        {hasNoMatch ? (
          <div className="absolute inset-0 z-10 bg-background">
            <CenteredHint>{t('emptyResults')}</CenteredHint>
          </div>
        ) : null}
      </div>

      {previewFile ? (
        <div className="absolute inset-0 z-10 bg-background">
          <WorkspaceFilePreview
            file={previewFile}
            workspace={workspaceDir}
            onClose={handleClosePreview}
            className="h-full"
          />
        </div>
      ) : null}
    </div>
  );
}
