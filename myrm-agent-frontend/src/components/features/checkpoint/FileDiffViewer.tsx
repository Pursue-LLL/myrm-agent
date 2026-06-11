'use client';

import React, { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { X, RotateCcw } from 'lucide-react';
import { FileChange, restoreFileSnapshot } from '@/services/checkpoint';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/hooks/useToast';

interface FileDiffViewerProps {
  snapshotId: string;
  changes: FileChange[];
  onClose: () => void;
  onRestoreSuccess?: (snapshotId: string, filesRestored: number) => void;
}

const changeTypeColors: Record<string, string> = {
  added: 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/30',
  modified: 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/30',
  deleted: 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30',
};

const changeTypeLabels: Record<string, string> = {
  added: '+',
  modified: '~',
  deleted: '-',
};

function formatSize(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return '-';
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function formatLineStat(change: FileChange): string | null {
  if (change.linesAdded === null && change.linesDeleted === null) return null;
  const parts: string[] = [];
  if (change.linesAdded !== null && change.linesAdded > 0) parts.push(`+${change.linesAdded}`);
  if (change.linesDeleted !== null && change.linesDeleted > 0) parts.push(`-${change.linesDeleted}`);
  return parts.length > 0 ? parts.join('/') : null;
}

const FileDiffViewer: React.FC<FileDiffViewerProps> = ({ snapshotId, changes, onClose, onRestoreSuccess }) => {
  const t = useTranslations('fileSnapshot');
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [restoring, setRestoring] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const added = changes.filter((c) => c.changeType === 'added');
  const modified = changes.filter((c) => c.changeType === 'modified');
  const deleted = changes.filter((c) => c.changeType === 'deleted');

  const toggleFile = useCallback((path: string) => {
    setSelectedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (selectedFiles.size === changes.length) {
      setSelectedFiles(new Set());
    } else {
      setSelectedFiles(new Set(changes.map((c) => c.path)));
    }
  }, [selectedFiles.size, changes]);

  const handleRestoreSelected = useCallback(async () => {
    if (selectedFiles.size === 0) return;
    setRestoring(true);
    setShowConfirm(false);
    try {
      const files = Array.from(selectedFiles);
      const response = await restoreFileSnapshot(snapshotId, files);
      if (response.success) {
        toast.success(t('restoreSuccess', { count: response.filesRestored }));
        onRestoreSuccess?.(snapshotId, response.filesRestored);
        setSelectedFiles(new Set());
      } else {
        toast.error(response.error || t('restoreError'));
      }
    } catch {
      toast.error(t('restoreError'));
    } finally {
      setRestoring(false);
    }
  }, [selectedFiles, snapshotId, t, onRestoreSuccess]);

  return (
    <div className="border border-border rounded-lg bg-card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-muted">
        <div className="text-sm font-medium text-foreground">
          {t('diffTitle', { snapshotId: snapshotId.slice(0, 12) })}
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {added.length > 0 && <span className="text-green-600 dark:text-green-400">+{added.length}</span>}
          {modified.length > 0 && <span className="text-yellow-600 dark:text-yellow-400">~{modified.length}</span>}
          {deleted.length > 0 && <span className="text-red-600 dark:text-red-400">-{deleted.length}</span>}
          <button onClick={onClose} className="p-0.5 rounded hover:bg-muted-foreground/10">
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="max-h-64 overflow-y-auto">
        {changes.length === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-muted-foreground">{t('noChanges')}</div>
        ) : (
          <>
            <div className="px-4 py-1.5 border-b border-border flex items-center gap-2">
              <input
                type="checkbox"
                checked={selectedFiles.size === changes.length && changes.length > 0}
                onChange={toggleAll}
                className="w-3.5 h-3.5 rounded border-border text-primary focus:ring-primary"
              />
              <span className="text-xs text-muted-foreground">
                {selectedFiles.size > 0 ? `${selectedFiles.size} / ${changes.length}` : t('selectAll')}
              </span>
            </div>
            <ul className="divide-y divide-border">
              {changes.map((change, idx) => {
                const lineStat = formatLineStat(change);
                return (
                  <li
                    key={`${change.path}-${idx}`}
                    className="px-4 py-1.5 flex items-center gap-2 text-xs font-mono hover:bg-muted/50 cursor-pointer"
                    onClick={() => toggleFile(change.path)}
                  >
                    <input
                      type="checkbox"
                      checked={selectedFiles.has(change.path)}
                      onChange={() => toggleFile(change.path)}
                      onClick={(e) => e.stopPropagation()}
                      className="w-3.5 h-3.5 rounded border-border text-primary focus:ring-primary"
                    />
                    <span
                      className={`inline-flex items-center justify-center w-4 h-4 rounded text-[10px] font-bold ${
                        changeTypeColors[change.changeType] || 'text-muted-foreground'
                      }`}
                    >
                      {changeTypeLabels[change.changeType] || '?'}
                    </span>
                    <span className="flex-1 truncate text-foreground">{change.path}</span>
                    {lineStat && (
                      <span className="text-[10px] font-mono text-muted-foreground whitespace-nowrap">
                        {lineStat}
                      </span>
                    )}
                    <span className="text-muted-foreground whitespace-nowrap">
                      {change.changeType === 'modified' ? (
                        <>
                          {formatSize(change.oldSize)} {'→'} {formatSize(change.newSize)}
                        </>
                      ) : change.changeType === 'added' ? (
                        formatSize(change.newSize)
                      ) : (
                        formatSize(change.oldSize)
                      )}
                    </span>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>

      {selectedFiles.size > 0 && (
        <div className="px-4 py-2 border-t border-border bg-muted flex items-center justify-between">
          {showConfirm ? (
            <div className="flex items-center gap-2 w-full">
              <span className="text-xs text-amber-600 dark:text-amber-400 flex-1">
                {t('confirmRestore', { count: selectedFiles.size })}
              </span>
              <button
                onClick={handleRestoreSelected}
                disabled={restoring}
                className="px-3 py-1 text-xs rounded-full bg-green-500 hover:bg-green-600 text-white disabled:opacity-50"
              >
                {restoring ? t('restoring') : t('confirmYes')}
              </button>
              <button
                onClick={() => setShowConfirm(false)}
                className="px-3 py-1 text-xs rounded-full bg-secondary hover:bg-secondary/80 text-secondary-foreground"
              >
                {t('confirmNo')}
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowConfirm(true)}
              disabled={restoring}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1 text-xs rounded-full transition-colors',
                'bg-green-500 hover:bg-green-600 text-white disabled:opacity-50',
              )}
            >
              <RotateCcw className="w-3 h-3" />
              {t('restoreSelected', { count: selectedFiles.size })}
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default FileDiffViewer;
