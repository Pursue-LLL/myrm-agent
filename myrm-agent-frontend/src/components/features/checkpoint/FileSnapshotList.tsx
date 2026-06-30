'use client';

import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { RefreshCw, Trash, Filter } from 'lucide-react';
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
import { useAgentNameMap } from '@/hooks/useAgentName';

interface FileSnapshotListProps {
  workingDir: string;
  onRestoreSuccess?: (snapshotId: string, filesRestored: number) => void;
}

const SSE_REFRESH_DEBOUNCE_MS = 500;

const FileSnapshotList: React.FC<FileSnapshotListProps> = ({ workingDir, onRestoreSuccess }) => {
  const t = useTranslations('fileSnapshot');
  const [snapshots, setSnapshots] = useState<FileSnapshotInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cleaningUp, setCleaningUp] = useState(false);
  const [showConfirmCleanup, setShowConfirmCleanup] = useState(false);
  const [diffSnapshotId, setDiffSnapshotId] = useState<string | null>(null);
  const [diffChanges, setDiffChanges] = useState<FileChange[]>([]);
  const [loadingDiff, setLoadingDiff] = useState(false);
  const [filterAgentId, setFilterAgentId] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const agentIds = useMemo(
    () => snapshots.map((s) => s.agentId),
    [snapshots],
  );
  const agentNameMap = useAgentNameMap(agentIds);

  const uniqueAgents = useMemo(() => {
    const seen = new Map<string, string>();
    for (const s of snapshots) {
      if (s.agentId && !seen.has(s.agentId)) {
        seen.set(s.agentId, agentNameMap.get(s.agentId) ?? s.agentId);
      }
    }
    return seen;
  }, [snapshots, agentNameMap]);

  const filteredSnapshots = useMemo(
    () => filterAgentId ? snapshots.filter((s) => s.agentId === filterAgentId) : snapshots,
    [snapshots, filterAgentId],
  );

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

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.meta_data?.type === 'snapshot_created') {
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => void loadSnapshots(), SSE_REFRESH_DEBOUNCE_MS);
      }
    };
    window.addEventListener('system-notification', handler);
    return () => {
      window.removeEventListener('system-notification', handler);
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
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
    setCleaningUp(true);
    setShowConfirmCleanup(false);
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
        <h2 className="text-lg font-semibold text-foreground">{t('title')}</h2>
        <div className="flex items-center gap-2">
          <button
            onClick={loadSnapshots}
            disabled={loading}
            className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-full transition-colors bg-secondary hover:bg-secondary/80 text-secondary-foreground disabled:opacity-50"
          >
            <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
            {t('refresh')}
          </button>
          {showConfirmCleanup ? (
            <div className="flex items-center gap-1">
              <button
                onClick={handleCleanup}
                disabled={cleaningUp}
                className="px-3 py-1.5 text-sm rounded-full bg-destructive hover:bg-destructive/90 text-destructive-foreground disabled:opacity-50"
              >
                {cleaningUp ? t('cleaning') : t('confirmYes')}
              </button>
              <button
                onClick={() => setShowConfirmCleanup(false)}
                className="px-3 py-1.5 text-sm rounded-full bg-secondary hover:bg-secondary/80 text-secondary-foreground"
              >
                {t('confirmNo')}
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowConfirmCleanup(true)}
              disabled={cleaningUp || loading}
              className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-full transition-colors bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-50"
            >
              <Trash className="w-4 h-4" />
              {t('cleanup')}
            </button>
          )}
        </div>
      </div>

      {uniqueAgents.size > 1 && (
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <Filter className="w-3.5 h-3.5 text-muted-foreground" />
          <button
            onClick={() => setFilterAgentId(null)}
            className={cn(
              'px-2 py-0.5 text-xs rounded-full transition-colors',
              !filterAgentId
                ? 'bg-primary text-primary-foreground'
                : 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
            )}
          >
            {t('allAgents')}
          </button>
          {Array.from(uniqueAgents.entries()).map(([id, name]) => (
            <button
              key={id}
              onClick={() => setFilterAgentId(filterAgentId === id ? null : id)}
              className={cn(
                'px-2 py-0.5 text-xs rounded-full transition-colors truncate max-w-[140px]',
                filterAgentId === id
                  ? 'bg-blue-500 text-white'
                  : 'bg-blue-500/15 text-blue-600 dark:text-blue-400 hover:bg-blue-500/25',
              )}
            >
              {name}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-destructive/10 text-destructive rounded-lg text-sm">
          {error}
        </div>
      )}

      {loading && snapshots.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">{t('loading')}</div>
      ) : snapshots.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">{t('noSnapshots')}</div>
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
              onRestoreSuccess={(id, count) => {
                onRestoreSuccess?.(id, count);
                loadSnapshots();
              }}
            />
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {filteredSnapshots.map((snapshot) => (
              <FileSnapshotCard
                key={snapshot.snapshotId}
                snapshot={snapshot}
                agentName={snapshot.agentId ? agentNameMap.get(snapshot.agentId) : undefined}
                onRestore={handleRestore}
                onViewDiff={handleViewDiff}
                onDelete={handleDelete}
                isLoading={loading || loadingDiff}
              />
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 text-xs text-muted-foreground text-center">
        {t('total', { count: filteredSnapshots.length })}
        {filterAgentId && ` / ${snapshots.length}`}
      </div>
    </div>
  );
};

export default FileSnapshotList;
