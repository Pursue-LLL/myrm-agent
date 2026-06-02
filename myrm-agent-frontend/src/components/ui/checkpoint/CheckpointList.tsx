'use client';

import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { RefreshCw, Trash } from 'lucide-react';
import CheckpointCard from './CheckpointCard';
import {
  listCheckpoints,
  resumeCheckpoint,
  deleteCheckpoint,
  cleanupCheckpoints,
  CheckpointInfo,
} from '@/services/checkpoint';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/hooks/useToast';

interface CheckpointListProps {
  sessionId?: string;
  onResumeSuccess?: (taskId: string, sessionId: string, checkpointData: Record<string, unknown>) => void;
}

const CheckpointList: React.FC<CheckpointListProps> = ({ sessionId, onResumeSuccess }) => {
  const t = useTranslations('checkpoint');
  const [checkpoints, setCheckpoints] = useState<CheckpointInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cleaningUp, setCleaningUp] = useState(false);

  const loadCheckpoints = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await listCheckpoints(sessionId);
      setCheckpoints(response.checkpoints);
    } catch (err) {
      console.error('Failed to load checkpoints:', err);
      setError(t('loadError'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCheckpoints();
  }, [sessionId]);

  const handleResume = async (taskId: string) => {
    setLoading(true);
    try {
      const response = await resumeCheckpoint(taskId);

      if (response.status === 'ready' && response.sessionId && response.checkpointData) {
        // Notify parent component with checkpoint data for restoration
        onResumeSuccess?.(taskId, response.sessionId, response.checkpointData);

        // Delete checkpoint after successful resume
        try {
          await deleteCheckpoint(taskId);
          setCheckpoints((prev) => prev.filter((cp) => cp.taskId !== taskId));
        } catch {
          // Non-critical: checkpoint will be cleaned up by TTL
        }

        toast.success(
          t('resumeSuccess', {
            agentType: response.sessionId,
            messagesCount: response.messagesCount,
          }),
        );
      }
    } catch (err) {
      console.error('Failed to resume checkpoint:', err);
      setError(t('resumeError'));
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (taskId: string) => {
    try {
      await deleteCheckpoint(taskId);
      // Remove from local state
      setCheckpoints((prev) => prev.filter((cp) => cp.taskId !== taskId));
    } catch (err) {
      console.error('Failed to delete checkpoint:', err);
      setError(t('deleteError'));
    }
  };

  const handleCleanup = async () => {
    if (!confirm(t('confirmCleanup'))) return;

    setCleaningUp(true);
    try {
      const response = await cleanupCheckpoints(7);
      // Reload checkpoints after cleanup
      await loadCheckpoints();

      // Show success message
      toast.success(t('cleanupSuccess', { deleted: response.deleted }));
    } catch (err) {
      console.error('Failed to cleanup checkpoints:', err);
      setError(t('cleanupError'));
    } finally {
      setCleaningUp(false);
    }
  };

  return (
    <div className="w-full max-w-4xl mx-auto p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('title')}</h2>
        <div className="flex items-center gap-2">
          <button
            onClick={loadCheckpoints}
            disabled={loading}
            className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-full transition-colors bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 disabled:opacity-50"
          >
            <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
            {t('refresh')}
          </button>
          <button
            onClick={handleCleanup}
            disabled={cleaningUp || loading}
            className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-full transition-colors bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-50"
          >
            <Trash className="w-4 h-4" />
            {cleaningUp ? t('cleaning') : t('cleanup')}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded-full text-sm">
          {error}
        </div>
      )}

      {loading && checkpoints.length === 0 ? (
        <div className="text-center py-8 text-gray-500 dark:text-gray-400">{t('loading')}</div>
      ) : checkpoints.length === 0 ? (
        <div className="text-center py-8 text-gray-500 dark:text-gray-400">{t('noCheckpoints')}</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {checkpoints.map((checkpoint) => (
            <CheckpointCard
              key={checkpoint.taskId}
              checkpoint={checkpoint}
              onResume={handleResume}
              onDelete={handleDelete}
              isLoading={loading}
            />
          ))}
        </div>
      )}

      <div className="mt-4 text-xs text-gray-500 dark:text-gray-400 text-center">
        {t('total', { count: checkpoints.length })}
      </div>
    </div>
  );
};

export default CheckpointList;
