'use client';

/**
 * Session Touched Files Inspection View.
 *
 * [INPUT] lucide-react, next-intl, ./worktreeTypes
 * [OUTPUT] SessionTouchedFilesPopover: Dialog/drawer displaying files modified or inspected in session.
 * [POS] src/components/features/git-worktree/SessionTouchedFilesPopover.tsx
 */

import { memo, useState, useMemo, useRef, useEffect } from 'react';
import {
  FileText,
  Search,
  X,
  FilePlus,
  FileEdit,
  FileX,
  Eye,
  Filter,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { SessionTouchedFile } from './worktreeTypes';

export interface SessionTouchedFilesPopoverProps {
  touchedFiles: SessionTouchedFile[];
  onClose: () => void;
  onSelectFile?: (filePath: string) => void;
}

export const SessionTouchedFilesPopover = memo(function SessionTouchedFilesPopover({
  touchedFiles,
  onClose,
  onSelectFile,
}: SessionTouchedFilesPopoverProps) {
  const t = useTranslations('gitWorktree');
  const [filterQuery, setFilterQuery] = useState('');
  const [selectedType, setSelectedType] = useState<string>('all');
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) {
      dialog.showModal();
    }
  }, []);

  const filteredFiles = useMemo(() => {
    return touchedFiles.filter((file) => {
      const matchText = file.file_path.toLowerCase().includes(filterQuery.toLowerCase());
      const matchType = selectedType === 'all' || file.change_type === selectedType;
      return matchText && matchType;
    });
  }, [touchedFiles, filterQuery, selectedType]);

  const renderBadge = (changeType: SessionTouchedFile['change_type']) => {
    switch (changeType) {
      case 'created':
        return (
          <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium">
            <FilePlus className="h-3 w-3" />
            <span>added</span>
          </span>
        );
      case 'deleted':
        return (
          <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-600 dark:text-rose-400 font-medium">
            <FileX className="h-3 w-3" />
            <span>deleted</span>
          </span>
        );
      case 'read':
        return (
          <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-medium">
            <Eye className="h-3 w-3" />
            <span>read</span>
          </span>
        );
      case 'modified':
      default:
        return (
          <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-600 dark:text-sky-400 font-medium">
            <FileEdit className="h-3 w-3" />
            <span>modified</span>
          </span>
        );
    }
  };

  return (
    <dialog
      ref={dialogRef}
      aria-modal="true"
      aria-labelledby="touched-files-title"
      onCancel={onClose}
      className={cn(
        'p-0 rounded-xl bg-background border border-border shadow-2xl backdrop:bg-black/50 backdrop:backdrop-blur-sm',
        'w-full max-w-lg m-auto text-foreground animate-in fade-in-0 zoom-in-95 duration-150',
      )}
      data-testid="session-touched-files-dialog"
    >
      <div className="flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" />
            <h3 id="touched-files-title" className="text-sm font-semibold">
              {t('touchedFilesTitle') || 'Session Touched Files'}
            </h3>
            <span className="text-xs font-mono bg-muted px-1.5 py-0.5 rounded-full text-muted-foreground">
              {touchedFiles.length}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground p-1 rounded-md"
            aria-label={t('close') || 'Close'}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Filter controls */}
        <div className="px-4 py-2 border-b border-border/40 flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="text"
              placeholder={t('searchFilesPlaceholder') || 'Filter touched files...'}
              value={filterQuery}
              onChange={(e) => {
                setFilterQuery(e.target.value);
              }}
              className="w-full pl-8 pr-2.5 py-1.5 text-xs rounded-lg border border-border bg-muted/40 focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div className="flex items-center gap-1 text-xs">
            <Filter className="h-3 w-3 text-muted-foreground" />
            <select
              value={selectedType}
              onChange={(e) => {
                setSelectedType(e.target.value);
              }}
              className="text-xs bg-muted/50 border border-border rounded-md px-2 py-1 focus:outline-none"
            >
              <option value="all">{t('allTypes') || 'All Types'}</option>
              <option value="modified">modified</option>
              <option value="created">created</option>
              <option value="deleted">deleted</option>
              <option value="read">read</option>
            </select>
          </div>
        </div>

        {/* File list */}
        <div className="overflow-y-auto p-2 flex-1 max-h-96 space-y-1">
          {filteredFiles.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              {t('noTouchedFilesFound') || 'No files matching criteria'}
            </div>
          ) : (
            filteredFiles.map((f) => (
              <button
                key={f.file_path}
                type="button"
                onClick={() => {
                  if (onSelectFile) {
                    onSelectFile(f.file_path);
                  }
                }}
                className={cn(
                  'w-full flex items-center justify-between px-2.5 py-2 rounded-lg text-left transition-colors',
                  'hover:bg-muted/60 focus:bg-muted/80 focus:outline-none border border-transparent hover:border-border/40',
                )}
              >
                <span className="font-mono text-xs truncate max-w-[340px] text-foreground">
                  {f.file_path}
                </span>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {renderBadge(f.change_type)}
                </div>
              </button>
            ))
          )}
        </div>
      </div>
    </dialog>
  );
});
