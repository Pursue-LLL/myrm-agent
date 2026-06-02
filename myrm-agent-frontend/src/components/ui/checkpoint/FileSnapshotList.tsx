'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { RefreshCw, Trash } from 'lucide-react';
import FileSnapshotCard from './FileSnapshotCard';
import FileDiffViewer from './FileDiffViewer';
import {
  listFileSnapshots,
  restoreFileSnapshot,
  deleteFileSnapshot,
  cleanupFileSnapshots,
  getFileSnapshotDiff,
  FileSnapshotInfo,
  FileChange,
} from '@/services/checkpoint';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/hooks/useToast';

interface FileSnapshotListProps {
  workingDir: string;
  onRestoreSuccess?: (snapshotId: string, filesRestored: number) => void;
}

const FileSnapshotList: React.FC<FileSnapshotListProps> = ({ workingDir, onRestoreSuccess }) => {
  const t = useTranslations('fileSnapshot');
  const [snapshots, setSnapshots] = useState<FileSnapshotInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cleaningUp, setCleaningUp] = useState(false);
  const [diffSnapshotId, setDiffSnapshotId] = useState<string | null>(null);
  const [diffChanges, setDiffChanges] = useState<FileChange[]>([]);
  const [loadingDiff, setLoadingDiff] = useState(false);

  const loadSnapshots = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await listFileSnapshots(workingDir);
      setSnapshots(response.snapshots);
    } catch (err) {
      console.error('Failed to load file snapshots:', err);
      setError(t('loadError'));
    } finally {
      setLoading(false);
    }
  }, [workingDir, t]);

  useEffect(() => {
    loadSnapshots();
  }, [loadSnapshots]);

  const handleRestore = async (snapshotId: string) => {
    setLoading(true);
    try {
      const response = await restoreFileSnapshot(snapshotId);
      if (response.success) {
        toast.success(t('restoreSuccess', { count: response.filesRestored }));
        onRestoreSuccess?.(snapshotId, response.filesRestored);
        await loadSnapshots();
      } else {
        setError(response.error || t('restoreError'));
      }
    } catch (err) {
      console.error('Failed to restore file snapshot:', err);
      setError(t('restoreError'));
    } finally {
      setLoading(false);
    }
  };

  const handleViewDiff = async (snapshotId: string) => {
    if (diffSnapshotId === snapshotId) {
      setDiffSnapshotId(null);
      setDiffChanges([]);
      return;
    }

    setLoadingDiff(true);
    try {
      const response = await getFileSnapshotDiff(snapshotId);
      setDiffSnapshotId(snapshotId);
      setDiffChanges(response.changes);
    } catch (err) {
      console.error('Failed to get file diff:', err);
      setError(t('diffError'));
    } finally {
      setLoadingDiff(false);
    }
  };

  const handleDelete = async (snapshotId: string) => {
    try {
      await deleteFileSnapshot(snapshotId);
      setSnapshots((prev) => prev.filter((s) => s.snapshotId !== snapshotId));
      if (diffSnapshotId === snapshotId) {
        setDiffSnapshotId(null);
        setDiffChanges([]);
      }
    } catch (err) {
      console.error('Failed to delete file snapshot:', err);
      setError(t('deleteError'));
    }
  };

  const handleCleanup = async () => {
    if (!confirm(t('confirmCleanup'))) return;

    setCleaningUp(true);
    try {
      const response = await cleanupFileSnapshots(workingDir, 20);
      await loadSnapshots();
      toast.success(t('cleanupSuccess', { deleted: response.deleted }));
    } catch (err) {
      console.error('Failed to cleanup file snapshots:', err);
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
            onClick={loadSnapshots}
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

      {loading && snapshots.length === 0 ? (
        <div className="text-center py-8 text-gray-500 dark:text-gray-400">{t('loading')}</div>
      ) : snapshots.length === 0 ? (
        <div className="text-center py-8 text-gray-500 dark:text-gray-400">{t('noSnapshots')}</div>
      ) : (
        <div className="space-y-3">
          {diffSnapshotId && (
            <FileDiffViewer
              snapshotId={diffSnapshotId}
              changes={diffChanges}
              onClose={() => {
                setDiffSnapshotId(null);
                setDiffChanges([]);
              }}
            />
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {snapshots.map((snapshot) => (
              <FileSnapshotCard
                key={snapshot.snapshotId}
                snapshot={snapshot}
                onRestore={handleRestore}
                onViewDiff={handleViewDiff}
                onDelete={handleDelete}
                isLoading={loading || loadingDiff}
              />
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 text-xs text-gray-500 dark:text-gray-400 text-center">
        {t('total', { count: snapshots.length })}
      </div>
    </div>
  );
};

export default FileSnapshotList;
