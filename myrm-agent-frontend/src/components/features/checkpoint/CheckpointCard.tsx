'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Clock, Trash2, RotateCcw } from 'lucide-react';
import { CheckpointInfo } from '@/services/checkpoint';
import { cn } from '@/lib/utils/classnameUtils';

interface CheckpointCardProps {
  checkpoint: CheckpointInfo;
  onReinitiate: (description: string, sessionId: string) => void;
  onDelete: (taskId: string) => void;
  isLoading?: boolean;
}

const CheckpointCard: React.FC<CheckpointCardProps> = ({
  checkpoint,
  onReinitiate,
  onDelete,
  isLoading = false,
}) => {
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

  const handleReinitiate = () => {
    onReinitiate(checkpoint.taskDescription || checkpoint.agentType, checkpoint.sessionId);
  };

  return (
    <div
      className={cn(
        'border border-gray-300 dark:border-gray-600 rounded-lg p-4 hover:shadow-md transition-shadow',
        isLoading && 'opacity-50 pointer-events-none',
      )}
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">{checkpoint.agentType}</h3>
          {checkpoint.taskDescription && (
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">{checkpoint.taskDescription}</p>
          )}
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 flex items-center gap-1">
            <Clock className="w-3 h-3 shrink-0" />
            {formattedDate}
          </p>
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
          onClick={handleReinitiate}
          disabled={isLoading}
          title={t('reinitiateTitle')}
          className={cn(
            'flex items-center gap-1 px-3 py-1.5 text-sm rounded-full transition-colors',
            'border border-purple-300 text-purple-600 hover:bg-purple-50 hover:text-purple-700',
            'dark:border-purple-800 dark:text-purple-400 dark:hover:bg-purple-900/20 dark:hover:text-purple-300',
            'disabled:opacity-50',
          )}
        >
          <RotateCcw className="w-3.5 h-3.5" />
          {t('reinitiateAction')}
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
