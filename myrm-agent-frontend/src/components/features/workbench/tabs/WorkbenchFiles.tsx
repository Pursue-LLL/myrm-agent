'use client';

/**
 * [INPUT]
 * - useChatStore from @/store/useChatStore (POS: workspaceDir of the current chat)
 * - useWorkspaceFiles, WorkspaceFileBrowser, WorkspaceFilePreview from @/components/features/workspace-browser
 *   (POS: the file tree, live refresh and preview shared with the sidebar workspace view)
 * - useWorkspaceFileSearch from ./useWorkspaceFileSearch (POS: file-name search over the whole workspace)
 * - useTranslations from next-intl (namespace: 'workbench.files')
 *
 * [OUTPUT]
 * - WorkbenchFiles: Files tab of the auxiliary workbench — the shared workspace browser, a name search laid
 *   over it while a query is typed, and the file preview laid over both
 *
 * [POS]
 * Files tab of the auxiliary workbench. It owns no file-reading logic: the tree, uploads, rename/move/delete
 * and previews all come from the workspace browser, so the workbench and the sidebar can never disagree.
 * The tree only reaches a few levels deep, so a typed name is searched on the server over the whole workspace.
 */

import React, { useCallback, useState } from 'react';
import dynamic from 'next/dynamic';
import { useTranslations } from 'next-intl';
import { FolderTree, Search } from 'lucide-react';
import { FileTypeIcon } from '@/components/features/files/FileTypeIcon';
import { useWorkspaceFiles } from '@/components/features/workspace-browser/useWorkspaceFiles';
import { cn } from '@/lib/utils/classnameUtils';
import type { FileEntry, WorkspaceFileSearchResult } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { useWorkspaceFileSearch, type WorkspaceFileSearchState } from './useWorkspaceFileSearch';

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

function CenteredHint({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-xs text-muted-foreground">
      <FolderTree className="h-8 w-8 opacity-40" />
      <span>{children}</span>
    </div>
  );
}

function toFileEntry(match: WorkspaceFileSearchResult): FileEntry {
  return {
    name: match.name,
    path: match.path,
    type: 'file',
    size: match.size,
    mtime: null,
    is_text: null,
    children: null,
  };
}

/** The folder part of a workspace-relative path: `src/lib/a.ts` gives `src/lib`. */
function parentFolder(relativePath: string, name: string): string {
  return relativePath.slice(0, Math.max(0, relativePath.length - name.length)).replace(/[\\/]$/, '');
}

function SearchResults({
  search,
  onOpen,
}: {
  search: WorkspaceFileSearchState;
  onOpen: (match: WorkspaceFileSearchResult) => void;
}) {
  const t = useTranslations('workbench.files');
  const { status, results } = search;

  if (status === 'failed') {
    return <CenteredHint>{t('searchFailed')}</CenteredHint>;
  }
  if (results.length === 0) {
    return status === 'done' ? <CenteredHint>{t('emptyResults')}</CenteredHint> : panelLoading;
  }
  return (
    <ul aria-busy={status === 'searching'} className={cn('py-1', status === 'searching' && 'opacity-60')}>
      {results.map((match) => (
        <li key={match.path}>
          <button
            type="button"
            onClick={() => onOpen(match)}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm transition-colors hover:bg-muted/50"
          >
            <FileTypeIcon filename={match.name} isDirectory={false} />
            <span className="shrink-0 truncate" title={match.name}>
              {match.name}
            </span>
            <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground" title={match.relative_path}>
              {parentFolder(match.relative_path, match.name)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function WorkbenchFiles() {
  const t = useTranslations('workbench.files');
  const workspaceDir = useChatStore((s) => s.workspaceDir);
  const { files, loading, error, truncated, refresh, loadChildren } = useWorkspaceFiles(workspaceDir);
  const [query, setQuery] = useState('');
  const [previewFile, setPreviewFile] = useState<FileEntry | null>(null);
  const search = useWorkspaceFileSearch(workspaceDir, query);

  const handleFileClick = useCallback((file: FileEntry) => {
    if (file.type === 'file') {
      setPreviewFile(file);
    }
  }, []);

  const handleOpenMatch = useCallback((match: WorkspaceFileSearchResult) => {
    setPreviewFile(toFileEntry(match));
  }, []);

  const handleClosePreview = useCallback(() => setPreviewFile(null), []);

  if (!workspaceDir) {
    return <CenteredHint>{t('workspaceUnavailable')}</CenteredHint>;
  }

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
        {/* Stays mounted under the search results, so the folders opened in the tree survive a search. */}
        <WorkspaceFileBrowser
          workspacePath={workspaceDir}
          files={files}
          loading={loading}
          error={error ? t('workspaceUnavailable') : null}
          truncated={truncated}
          onRefresh={refresh}
          onFileClick={handleFileClick}
          onLoadChildren={loadChildren}
          className="h-full"
        />
        {search.status !== 'idle' ? (
          <div className="absolute inset-0 z-10 overflow-y-auto bg-background">
            <SearchResults search={search} onOpen={handleOpenMatch} />
          </div>
        ) : null}
      </div>

      {previewFile ? (
        <div className="absolute inset-0 z-20 bg-background">
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
