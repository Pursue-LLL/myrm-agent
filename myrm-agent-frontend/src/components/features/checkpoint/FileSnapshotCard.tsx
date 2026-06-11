'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { RotateCcw, Eye, Trash } from 'lucide-react';
import { FileSnapshotInfo } from '@/services/checkpoint';
import { cn } from '@/lib/utils/classnameUtils';

interface FileSnapshotCardProps {
  snapshot: FileSnapshotInfo;
  onRestore: (snapshotId: string) => void;
  onViewDiff: (snapshotId: string) => void;
  onDelete: (snapshotId: string) => void;
  isLoading: boolean;
}

const triggerLabels: Record<string, string> = {
  write_file: 'Write',
  delete_file: 'Delete',
  patch_file: 'Patch',
  execute_terminal: 'Terminal',
  manual: 'Manual',
  pre_rollback: 'Pre-rollback',
};

const FileSnapshotCard: React.FC<FileSnapshotCardProps> = ({
  snapshot,
  onRestore,
  onViewDiff,
  onDelete,
  isLoading,
}) => {
  const t = useTranslations('fileSnapshot');
  const [showConfirmRestore, setShowConfirmRestore] = useState(false);
  const date = new Date(snapshot.createdAt * 1000);
  const timeStr = date.toLocaleString();
  const triggerLabel = triggerLabels[snapshot.trigger] || snapshot.trigger;

  return (
    <div className="border border-border rounded-lg p-4 bg-card">
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-primary/10 text-primary">
              {triggerLabel}
            </span>
            <span className="text-xs text-muted-foreground">
              {t('filesCount', { count: snapshot.fileCount })}
            </span>
          </div>
          {snapshot.description && (
            <p className="text-sm text-foreground truncate">{snapshot.description}</p>
          )}
        </div>
      </div>

      <div className="text-xs text-muted-foreground mb-3">{timeStr}</div>

      <div className="flex items-center gap-2">
        {showConfirmRestore ? (
          <>
            <button
              onClick={() => {
                onRestore(snapshot.snapshotId);
                setShowConfirmRestore(false);
              }}
              disabled={isLoading}
              className={cn(
                'flex items-center gap-1 px-2.5 py-1 text-xs rounded-full transition-colors',
                'bg-green-500 hover:bg-green-600 text-white disabled:opacity-50',
              )}
            >
              {t('confirmYes')}
            </button>
            <button
              onClick={() => setShowConfirmRestore(false)}
              className="px-2.5 py-1 text-xs rounded-full bg-secondary hover:bg-secondary/80 text-secondary-foreground"
            >
              {t('confirmNo')}
            </button>
          </>
        ) : (
          <button
            onClick={() => setShowConfirmRestore(true)}
            disabled={isLoading}
            className={cn(
              'flex items-center gap-1 px-2.5 py-1 text-xs rounded-full transition-colors',
              'bg-green-500 hover:bg-green-600 text-white disabled:opacity-50',
            )}
          >
            <RotateCcw className="w-3 h-3" />
            {t('restore')}
          </button>
        )}
        <button
          onClick={() => onViewDiff(snapshot.snapshotId)}
          disabled={isLoading}
          className={cn(
            'flex items-center gap-1 px-2.5 py-1 text-xs rounded-full transition-colors',
            'bg-secondary hover:bg-secondary/80 text-secondary-foreground disabled:opacity-50',
          )}
        >
          <Eye className="w-3 h-3" />
          {t('diff')}
        </button>
        <button
          onClick={() => onDelete(snapshot.snapshotId)}
          disabled={isLoading}
          className={cn(
            'flex items-center gap-1 px-2.5 py-1 text-xs rounded-full transition-colors',
            'bg-destructive/10 hover:bg-destructive/20 text-destructive disabled:opacity-50',
          )}
        >
          <Trash className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
};

export default FileSnapshotCard;
