'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import {
  IconFolder,
  IconPlus,
  IconTrash,
  IconRefresh,
  IconLoader,
  IconHardDrive,
} from '@/components/ui/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import {
  getLocalFileSearchConfig,
  getIndexStats,
  addDirectory,
  removeDirectory,
  updateDirectory,
  triggerIndex,
  type DirectoryConfig,
  type IndexStats,
} from '@/services/localFileSearch';

export default function LocalFileSearchSection() {
  const t = useTranslations('localFileSearch');
  const [directories, setDirectories] = useState<DirectoryConfig[]>([]);
  const [stats, setStats] = useState<IndexStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isIndexing, setIsIndexing] = useState(false);
  const [newPath, setNewPath] = useState('');
  const [newRecursive, setNewRecursive] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const loadConfig = useCallback(async () => {
    try {
      setIsLoading(true);
      const config = await getLocalFileSearchConfig();
      setDirectories(config.directories);
      setStats(config.stats);
    } catch {
      toast.error('Failed to load local file search configuration');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  useEffect(() => {
    if (!stats || stats.status !== 'indexing') return;

    const interval = setInterval(async () => {
      try {
        const latestStats = await getIndexStats();
        setStats(latestStats);
        if (latestStats.status !== 'indexing') {
          setIsIndexing(false);
        }
      } catch {
        /* ignore polling errors */
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [stats?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleAddDirectory = async () => {
    if (!newPath.trim()) return;
    try {
      const dir = await addDirectory(newPath.trim(), newRecursive);
      setDirectories((prev) => [...prev, dir]);
      setNewPath('');
      setShowAddForm(false);
      toast.success(`Directory added: ${dir.path}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to add directory';
      toast.error(msg);
    }
  };

  const handleRemoveDirectory = async (id: string) => {
    setRemovingId(id);
    try {
      await removeDirectory(id);
      setDirectories((prev) => prev.filter((d) => d.id !== id));
      toast.success(t('removeDirectory'));
    } catch {
      toast.error('Failed to remove directory');
    } finally {
      setRemovingId(null);
    }
  };

  const handleToggleEnabled = async (id: string, enabled: boolean) => {
    try {
      const updated = await updateDirectory(id, { enabled });
      setDirectories((prev) => prev.map((d) => (d.id === id ? updated : d)));
    } catch {
      toast.error('Failed to update directory');
    }
  };

  const handleTriggerIndex = async () => {
    setIsIndexing(true);
    try {
      const newStats = await triggerIndex();
      setStats(newStats);
      toast.success('Indexing started');
    } catch (err) {
      setIsIndexing(false);
      const msg = err instanceof Error ? err.message : 'Failed to start indexing';
      toast.error(msg);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <IconLoader className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const isCurrentlyIndexing = stats?.status === 'indexing' || isIndexing;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-foreground">{t('title')}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('description')}</p>
      </div>

      {/* Statistics */}
      {stats && (stats.total_files > 0 || isCurrentlyIndexing) && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <IconHardDrive className="size-4" />
              {t('stats')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <StatItem label={t('totalFiles')} value={stats.total_files.toLocaleString()} />
              <StatItem label={t('totalChunks')} value={stats.total_chunks.toLocaleString()} />
              <StatItem label={t('errors')} value={String(stats.error_count)} warning={stats.error_count > 0} />
              <StatItem
                label={t('lastIndexed')}
                value={stats.last_indexed_at ? new Date(stats.last_indexed_at).toLocaleDateString() : t('never')}
              />
            </div>
            {isCurrentlyIndexing && (
              <div className="mt-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{t('progress')}</span>
                  <span className="font-medium">{Math.round(stats.indexing_progress * 100)}%</span>
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all duration-500"
                    style={{ width: `${stats.indexing_progress * 100}%` }}
                  />
                </div>
                {stats.current_file && (
                  <p className="mt-1 truncate text-xs text-muted-foreground">{stats.current_file}</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Directories */}
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <IconFolder className="size-4" />
                {t('directories')}
              </CardTitle>
              <CardDescription className="mt-1">{t('addDirectoryDesc')}</CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleTriggerIndex}
                disabled={isCurrentlyIndexing || directories.length === 0}
              >
                {isCurrentlyIndexing ? (
                  <>
                    <IconLoader className="mr-1.5 size-3.5 animate-spin" />
                    {t('indexing')}
                  </>
                ) : (
                  <>
                    <IconRefresh className="mr-1.5 size-3.5" />
                    {t('indexNow')}
                  </>
                )}
              </Button>
              <Button variant="default" size="sm" onClick={() => setShowAddForm(!showAddForm)}>
                <IconPlus className="mr-1.5 size-3.5" />
                {t('addDirectory')}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Add Directory Form */}
          {showAddForm && (
            <div className="space-y-3 rounded-lg border border-dashed border-border bg-muted/30 p-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">{t('directoryPath')}</label>
                <Input
                  value={newPath}
                  onChange={(e) => setNewPath(e.target.value)}
                  placeholder={t('directoryPathPlaceholder')}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddDirectory()}
                />
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Switch checked={newRecursive} onCheckedChange={setNewRecursive} id="recursive-toggle" />
                  <label htmlFor="recursive-toggle" className="text-sm text-muted-foreground">
                    {t('recursive')}
                  </label>
                </div>
                <Button onClick={handleAddDirectory} disabled={!newPath.trim()} size="sm">
                  {t('addDirectory')}
                </Button>
              </div>
            </div>
          )}

          {/* Directory List */}
          {directories.length === 0 && !showAddForm && (
            <p className="py-8 text-center text-sm text-muted-foreground">{t('noDirectories')}</p>
          )}

          {directories.map((dir) => (
            <div
              key={dir.id}
              className={cn(
                'flex items-center justify-between rounded-lg border border-border px-4 py-3 transition-colors',
                !dir.enabled && 'opacity-50',
              )}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-sm text-foreground">{dir.path}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {dir.recursive ? t('recursive') : 'Top-level only'}
                  {' · '}
                  {dir.enabled ? t('enabled') : t('disabled')}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Switch checked={dir.enabled} onCheckedChange={(checked) => handleToggleEnabled(dir.id, checked)} />
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleRemoveDirectory(dir.id)}
                  disabled={removingId === dir.id}
                  className="text-destructive hover:bg-destructive/10"
                >
                  {removingId === dir.id ? (
                    <IconLoader className="size-4 animate-spin" />
                  ) : (
                    <IconTrash className="size-4" />
                  )}
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function StatItem({ label, value, warning }: { label: string; value: string; warning?: boolean }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={cn('text-lg font-semibold', warning ? 'text-destructive' : 'text-foreground')}>{value}</p>
    </div>
  );
}
