'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { X } from 'lucide-react';
import { FileChange } from '@/services/checkpoint';

interface FileDiffViewerProps {
  snapshotId: string;
  changes: FileChange[];
  onClose: () => void;
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

const FileDiffViewer: React.FC<FileDiffViewerProps> = ({ snapshotId, changes, onClose }) => {
  const t = useTranslations('fileSnapshot');

  const added = changes.filter((c) => c.changeType === 'added');
  const modified = changes.filter((c) => c.changeType === 'modified');
  const deleted = changes.filter((c) => c.changeType === 'deleted');

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
        <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {t('diffTitle', { snapshotId: snapshotId.slice(0, 12) })}
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
          {added.length > 0 && <span className="text-green-600 dark:text-green-400">+{added.length}</span>}
          {modified.length > 0 && <span className="text-yellow-600 dark:text-yellow-400">~{modified.length}</span>}
          {deleted.length > 0 && <span className="text-red-600 dark:text-red-400">-{deleted.length}</span>}
          <button onClick={onClose} className="p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700">
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="max-h-64 overflow-y-auto">
        {changes.length === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-gray-500 dark:text-gray-400">{t('noChanges')}</div>
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-gray-700">
            {changes.map((change, idx) => (
              <li key={`${change.path}-${idx}`} className="px-4 py-1.5 flex items-center gap-2 text-xs font-mono">
                <span
                  className={`inline-flex items-center justify-center w-4 h-4 rounded text-[10px] font-bold ${
                    changeTypeColors[change.changeType] || 'text-gray-500'
                  }`}
                >
                  {changeTypeLabels[change.changeType] || '?'}
                </span>
                <span className="flex-1 truncate text-gray-800 dark:text-gray-200">{change.path}</span>
                <span className="text-gray-400 dark:text-gray-500 whitespace-nowrap">
                  {change.changeType === 'modified' ? (
                    <>
                      {formatSize(change.oldSize)} {'->'} {formatSize(change.newSize)}
                    </>
                  ) : change.changeType === 'added' ? (
                    formatSize(change.newSize)
                  ) : (
                    formatSize(change.oldSize)
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

export default FileDiffViewer;
