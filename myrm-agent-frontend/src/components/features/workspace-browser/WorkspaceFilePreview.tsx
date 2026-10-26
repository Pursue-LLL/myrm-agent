'use client';

/**
 * Workspace file content preview and editor
 *
 * [INPUT]
 * - file: FileEntry to preview/edit
 * - workspace: Workspace root path for API calls
 * - onDirtyChange: told whether the file holds edits that are not saved yet (false again when the preview goes away)
 * - useWorkspaceTextEditor (POS: read, draft, save-against-version, conflict and copy handling)
 * - RichMediaFilePreview::getPreviewKind (POS: workspace rich-media dispatch)
 *
 * [OUTPUT]
 * - WorkspaceFilePreview: Full-height panel showing file content with line numbers, edit mode toggle, and
 *   Ctrl+S save. Binary files (images/audio/video/PDF/office docs) are rendered by RichMediaFilePreview.
 *   A file the editor cannot change safely is shown view-only with a localized reason; a file that changed on
 *   disk during an edit keeps the user's text and offers load-latest / overwrite / save-as-copy.
 *   A file that cannot be read gets a localized notice; the server's reason is never shown.
 *
 * [POS]
 * File content preview/editor for the workspace browser. Text is read together with its version, so a save can
 * never silently replace what changed on disk meanwhile. Supports inline editing with Ctrl+S / Cmd+S keyboard
 * save shortcut (ignored while the preview sits in a hidden tab panel). Routes binary files to the rich media
 * renderer dispatcher.
 */

import React, { memo, useEffect, useState, useCallback, useRef } from 'react';
import { X, Download, RefreshCw, FileText, AlertTriangle, Pencil, Save, Eye, GitCommit } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { FileTypeIcon } from '@/components/features/files/FileTypeIcon';
import { getWorkspaceFileContentUrl, type FileEntry } from '@/services/chat';
import { getPreviewKind, RichMediaFilePreview, type PreviewKind } from './RichMediaFilePreview';
import { InlineWorkspaceDiff } from './InlineWorkspaceDiff';
import { ConflictNotice, ReadonlyNotice } from './WorkspaceTextNotices';
import { formatBytes, getLanguage, LineNumberedCode, LineNumberedEditor } from './WorkspaceTextViews';
import { useWorkspaceTextEditor } from './useWorkspaceTextEditor';

interface WorkspaceFilePreviewProps {
  file: FileEntry;
  workspace: string;
  onClose: () => void;
  onDirtyChange?: (dirty: boolean) => void;
  className?: string;
}

export const WorkspaceFilePreview: React.FC<WorkspaceFilePreviewProps> = memo(
  ({ file, workspace, onClose, onDirtyChange, className }) => {
    const t = useTranslations('workspace');
    const [editing, setEditing] = useState(false);
    const [showDiff, setShowDiff] = useState(false);
    const rootRef = useRef<HTMLDivElement>(null);

    const previewKind = getPreviewKind(file.name);
    // Unknown extensions defer to the backend is_text flag: binary files render
    // the download fallback instead of garbled text.
    const listedKind: PreviewKind | null = previewKind ?? (file.is_text === false ? 'unsupported' : null);
    // Only text files support inline editing; SVG needs its text fetched to render.
    const needsText = listedKind === null || previewKind === 'svg';

    const editor = useWorkspaceTextEditor(workspace, file.path, needsText);
    const { snapshot, dirty, save, discard } = editor;
    const loading = editor.phase === 'loading';
    const loadFailed = editor.phase === 'failed';
    // A file the listing took for text can still hold binary data; it has no text to show.
    const effectiveKind: PreviewKind | null =
      listedKind ?? (snapshot?.readonlyReason === 'binary' ? 'unsupported' : null);
    const isRichMedia = effectiveKind !== null;
    const canEdit = !isRichMedia && snapshot?.editable === true;
    const readonlyReason = !isRichMedia && snapshot ? snapshot.readonlyReason : null;

    // A different file starts in view mode.
    useEffect(() => {
      setEditing(false);
      setShowDiff(false);
    }, [file.path, workspace]);

    // The host learns of unsaved edits for as long as they exist, and that they are gone once this preview is.
    useEffect(() => {
      onDirtyChange?.(dirty);
      return () => onDirtyChange?.(false);
    }, [dirty, onDirtyChange]);

    const toggleEdit = useCallback(() => {
      if (editing && dirty) {
        if (!window.confirm(t('discardConfirm'))) {
          return;
        }
        discard();
      }
      setEditing((prev) => !prev);
    }, [editing, dirty, discard, t]);

    // Ctrl+S / Cmd+S, unless a host keeps this preview mounted but hidden (the workbench does so under its Terminal tab)
    useEffect(() => {
      const handler = (e: globalThis.KeyboardEvent) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 's' && editing && !rootRef.current?.closest('[hidden]')) {
          e.preventDefault();
          void save();
        }
      };
      window.addEventListener('keydown', handler);
      return () => window.removeEventListener('keydown', handler);
    }, [editing, save]);

    const handleDownload = useCallback(() => {
      const url = getWorkspaceFileContentUrl(file.path, workspace, true);
      window.open(url, '_blank', 'noopener,noreferrer');
    }, [file.path, workspace]);

    const handleClose = useCallback(() => {
      if (editing && dirty && !window.confirm(t('discardConfirm'))) {
        return;
      }
      onClose();
    }, [editing, dirty, onClose, t]);

    const language = getLanguage(file.name);
    const size = snapshot?.size ?? file.size;

    return (
      <div
        ref={rootRef}
        data-testid="workspace-file-preview"
        className={cn('flex flex-col h-full bg-background', className)}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <FileTypeIcon filename={file.name} className="shrink-0" />
            <span className="text-sm font-medium truncate" title={file.path}>
              {file.name}
            </span>
            {dirty && <span className="text-xs text-warning shrink-0">{t('unsaved')}</span>}
            {size !== null && !dirty && (
              <span className="text-xs text-muted-foreground shrink-0">{formatBytes(size)}</span>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {canEdit && (
              <>
                {dirty && (
                  <button
                    onClick={() => setShowDiff((prev) => !prev)}
                    className={cn('p-1 rounded hover:bg-muted transition-colors', showDiff && 'bg-muted')}
                    title={t('diffView')}
                  >
                    <GitCommit className="h-4 w-4 text-emerald-500" />
                  </button>
                )}
                <button
                  onClick={toggleEdit}
                  className={cn('p-1 rounded hover:bg-muted transition-colors', editing && 'bg-muted')}
                  title={editing ? t('viewMode') : t('editMode')}
                >
                  {editing ? (
                    <Eye className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <Pencil className="h-4 w-4 text-muted-foreground" />
                  )}
                </button>
              </>
            )}
            {canEdit && editing && dirty && (
              <button
                onClick={() => void save()}
                disabled={editor.saving}
                className="p-1 rounded hover:bg-muted transition-colors"
                title={`${t('save')} (Ctrl+S)`}
              >
                <Save
                  className={cn('h-4 w-4', editor.saving ? 'animate-spin text-muted-foreground' : 'text-primary')}
                />
              </button>
            )}
            <button
              onClick={handleDownload}
              className="p-1 rounded hover:bg-muted transition-colors"
              title={t('download')}
            >
              <Download className="h-4 w-4 text-muted-foreground" />
            </button>
            <button onClick={handleClose} className="p-1 rounded hover:bg-muted transition-colors" title={t('close')}>
              <X className="h-4 w-4 text-muted-foreground" />
            </button>
          </div>
        </div>

        {/* Notices */}
        {(editor.conflict || (readonlyReason !== null && readonlyReason !== 'binary')) && (
          <div className="shrink-0 pt-2">
            {editor.conflict && (
              <ConflictNotice
                busy={editor.saving}
                onSaveCopy={() => void editor.saveCopy()}
                onReload={() => void editor.reload()}
                onOverwrite={() => void editor.overwrite()}
              />
            )}
            {readonlyReason !== null && readonlyReason !== 'binary' && <ReadonlyNotice reason={readonlyReason} />}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-auto py-2">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : loadFailed ? (
            <div className="flex flex-col items-center justify-center h-full px-4 text-muted-foreground">
              <AlertTriangle className="h-6 w-6 mb-2 text-destructive" />
              <span className="text-sm text-center">{t('previewLoadError')}</span>
            </div>
          ) : showDiff && snapshot !== null ? (
            <InlineWorkspaceDiff
              file={file}
              workspace={workspace}
              originalContent={snapshot.content}
              modifiedContent={editor.draft}
              onClose={() => setShowDiff(false)}
            />
          ) : isRichMedia ? (
            previewKind !== 'svg' || snapshot !== null ? (
              <RichMediaFilePreview
                filePath={file.path}
                filename={file.name}
                workspace={workspace}
                content={snapshot?.content}
                kind={effectiveKind ?? undefined}
                onDownload={handleDownload}
              />
            ) : null
          ) : snapshot !== null ? (
            editing && canEdit ? (
              <LineNumberedEditor content={editor.draft} onChange={editor.setDraft} />
            ) : (
              <LineNumberedCode content={snapshot.content} language={language} />
            )
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
              <FileText className="h-8 w-8 mb-2" />
              <span className="text-sm">{t('noContent')}</span>
            </div>
          )}
        </div>
      </div>
    );
  },
);

WorkspaceFilePreview.displayName = 'WorkspaceFilePreview';
