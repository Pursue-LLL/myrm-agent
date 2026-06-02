'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Clock, Trash2, Play } from 'lucide-react';
import { CheckpointInfo } from '@/services/checkpoint';
import { cn } from '@/lib/utils/classnameUtils';

interface CheckpointCardProps {
  checkpoint: CheckpointInfo;
  onResume: (taskId: string) => void;
  onDelete: (taskId: string) => void;
  isLoading?: boolean;
}

const CheckpointCard: React.FC<CheckpointCardProps> = ({ checkpoint, onResume, onDelete, isLoading = false }) => {
  const t = useTranslations('checkpoint');
  const [deleting, setDeleting] = useState(false);

  const formattedDate = new Date(checkpoint.timestamp * 1000).toLocaleString();
  const progressPercentage = Math.round(checkpoint.progress * 100);

  const handleDelete = async () => {
    if (confirm(t('confirmDelete'))) {
      setDeleting(true);
      try {
        await onDelete(checkpoint.taskId);
      } catch (error) {
        console.error('Delete checkpoint failed:', error);
      } finally {
        setDeleting(false);
      }
    }
  };

  const handleResume = () => {
    onResume(checkpoint.taskId);
  };

  return (
    <div
      className={cn(
        'border border-gray-300 dark:border-gray-600 rounded-lg p-4 hover:shadow-md transition-shadow',
        isLoading && 'opacity-50 pointer-events-none',
      )}
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">{checkpoint.agentType}</h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {formattedDate}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'text-xs px-2 py-1 rounded-full',
              checkpoint.resumable
                ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
                : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
            )}
          >
            {checkpoint.resumable ? t('resumable') : t('notResumable')}
          </span>
        </div>
      </div>

      <div className="mb-3">
        <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
          <span>{t('progress')}</span>
          <span>{progressPercentage}%</span>
        </div>
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
          <div
            className="bg-blue-500 dark:bg-blue-400 h-2 rounded-full transition-all"
            style={{ width: `${progressPercentage}%` }}
          />
        </div>
      </div>

      {checkpoint.lastTool && (
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
          {t('lastTool')}: <span className="font-mono">{checkpoint.lastTool}</span>
        </p>
      )}

      <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
        <button
          onClick={handleResume}
          disabled={!checkpoint.resumable || isLoading}
          className={cn(
            'flex items-center gap-1 px-3 py-1.5 text-sm rounded-full transition-colors',
            checkpoint.resumable && !isLoading
              ? 'bg-blue-500 hover:bg-blue-600 text-white'
              : 'bg-gray-300 dark:bg-gray-600 text-gray-500 dark:text-gray-400 cursor-not-allowed',
          )}
        >
          <Play className="w-3.5 h-3.5" />
          {t('resume')}
        </button>
        <button
          onClick={handleDelete}
          disabled={deleting || isLoading}
          className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-full transition-colors bg-red-500 hover:bg-red-600 text-white disabled:bg-gray-300 disabled:text-gray-500 dark:disabled:bg-gray-600 dark:disabled:text-gray-400"
        >
          <Trash2 className="w-3.5 h-3.5" />
          {deleting ? t('deleting') : t('delete')}
        </button>
      </div>
    </div>
  );
};

export default CheckpointCard;
