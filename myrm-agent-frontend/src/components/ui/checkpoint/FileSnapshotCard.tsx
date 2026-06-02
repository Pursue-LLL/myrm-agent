'use client';

import React from 'react';
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
  const date = new Date(snapshot.createdAt * 1000);
  const timeStr = date.toLocaleString();
  const triggerLabel = triggerLabels[snapshot.trigger] || snapshot.trigger;

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-white dark:bg-gray-800">
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200">
              {triggerLabel}
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {t('filesCount', { count: snapshot.fileCount })}
            </span>
          </div>
          {snapshot.description && (
            <p className="text-sm text-gray-700 dark:text-gray-300 truncate">{snapshot.description}</p>
          )}
        </div>
      </div>

      <div className="text-xs text-gray-500 dark:text-gray-400 mb-3">{timeStr}</div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => onRestore(snapshot.snapshotId)}
          disabled={isLoading}
          className={cn(
            'flex items-center gap-1 px-2.5 py-1 text-xs rounded-full transition-colors',
            'bg-green-500 hover:bg-green-600 text-white disabled:opacity-50',
          )}
        >
          <RotateCcw className="w-3 h-3" />
          {t('restore')}
        </button>
        <button
          onClick={() => onViewDiff(snapshot.snapshotId)}
          disabled={isLoading}
          className={cn(
            'flex items-center gap-1 px-2.5 py-1 text-xs rounded-full transition-colors',
            'bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600',
            'text-gray-700 dark:text-gray-300 disabled:opacity-50',
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
            'bg-red-100 hover:bg-red-200 dark:bg-red-900 dark:hover:bg-red-800',
            'text-red-700 dark:text-red-300 disabled:opacity-50',
          )}
        >
          <Trash className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
};

export default FileSnapshotCard;
