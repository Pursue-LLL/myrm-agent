'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { IconDownload, IconHardDrive, IconRefresh, IconTrash, IconUpload } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/primitives/alert-dialog';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Checkbox } from '@/components/primitives/checkbox';

interface BackupMetadata {
  backup_id: string;
  created_at: string;
  memory_count: number;
  size_bytes: number;
  collections: string[];
  description?: string;
}

export default function MemoryBackupSection() {
  const t = useTranslations('settings.memoryBackup');
  const [backups, setBackups] = useState<BackupMetadata[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [description, setDescription] = useState('');
  const [restoreOverwrite, setRestoreOverwrite] = useState(false);

  const loadBackups = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/memory/backup/list', {
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Failed to load backups');
      const data = await response.json();
      setBackups(data.backups || []);
    } catch (error) {
      toast.error(t('loadError') || 'Failed to load backups');
      console.error('Load backups error:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadBackups();
  }, []);

  const createBackup = async () => {
    try {
      setCreating(true);
      const response = await fetch('/api/v1/memory/backup/create', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: description.trim() || undefined }),
      });
      if (!response.ok) throw new Error('Failed to create backup');
      const data = await response.json();
      if (data.success) {
        toast.success(t('createSuccess') || 'Backup created successfully');
        setDescription('');
        await loadBackups();
      } else {
        throw new Error(data.error || 'Unknown error');
      }
    } catch (error) {
      toast.error(t('createError') || 'Failed to create backup');
      console.error('Create backup error:', error);
    } finally {
      setCreating(false);
    }
  };

  const restoreBackup = async (backupId: string) => {
    try {
      const response = await fetch('/api/v1/memory/backup/restore', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backup_id: backupId, overwrite: restoreOverwrite }),
      });
      if (!response.ok) throw new Error('Failed to restore backup');
      const data = await response.json();
      if (data.success) {
        toast.success(
          t('restoreSuccess', { count: data.restored_count ?? 0 }) || `Restored ${data.restored_count} memories`,
        );
      } else {
        throw new Error(data.error || 'Unknown error');
      }
    } catch (error) {
      toast.error(t('restoreError') || 'Failed to restore backup');
      console.error('Restore backup error:', error);
    }
  };

  const deleteBackup = async (backupId: string) => {
    try {
      const response = await fetch(`/api/v1/memory/backup/${backupId}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Failed to delete backup');
      toast.success(t('deleteSuccess') || 'Backup deleted');
      await loadBackups();
    } catch (error) {
      toast.error(t('deleteError') || 'Failed to delete backup');
      console.error('Delete backup error:', error);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / k ** i).toFixed(2)} ${sizes[i]}`;
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t('title') || 'Memory Backup'}</CardTitle>
          <CardDescription>
            {t('description') || 'Backup and restore your memory data for data safety.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="backup-description">{t('descriptionLabel') || 'Description (Optional)'}</Label>
            <Input
              id="backup-description"
              placeholder={t('descriptionPlaceholder') || 'E.g., Before major update'}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <Button onClick={createBackup} disabled={creating} className="w-full">
            <IconDownload className="mr-2 h-4 w-4" />
            {creating ? t('creating') || 'Creating...' : t('createBackup') || 'Create Backup'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>{t('backupListTitle') || 'Backup History'}</CardTitle>
            <CardDescription>{t('backupListDescription', { count: backups.length })}</CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={loadBackups} disabled={loading}>
            <IconRefresh className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-8 text-muted-foreground">{t('loading') || 'Loading...'}</div>
          ) : backups.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">{t('noBackups') || 'No backups found'}</div>
          ) : (
            <div className="space-y-3">
              {backups.map((backup) => (
                <div
                  key={backup.backup_id}
                  className="flex items-center justify-between p-4 border rounded-lg hover:bg-accent/50 transition-colors"
                >
                  <div className="flex-1 space-y-1">
                    <div className="flex items-center gap-2">
                      <IconHardDrive className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{backup.description || backup.backup_id}</span>
                    </div>
                    <div className="text-sm text-muted-foreground space-y-0.5">
                      <div>{formatDate(backup.created_at)}</div>
                      <div>
                        {backup.memory_count} {t('memories') || 'memories'} · {formatBytes(backup.size_bytes)}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="outline" size="sm">
                          <IconUpload className="mr-2 h-4 w-4" />
                          {t('restore') || 'Restore'}
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>{t('restoreTitle') || 'Restore Backup'}</AlertDialogTitle>
                          <AlertDialogDescription>
                            {t('restoreWarning') || 'This will restore memories from the backup.'}
                          </AlertDialogDescription>
                          <div className="flex items-center space-x-2 pt-2">
                            <Checkbox
                              id={`overwrite-${backup.backup_id}`}
                              checked={restoreOverwrite}
                              onCheckedChange={(checked) => setRestoreOverwrite(checked as boolean)}
                            />
                            <label
                              htmlFor={`overwrite-${backup.backup_id}`}
                              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                            >
                              {t('overwriteExisting') || 'Clear existing memories before restore'}
                            </label>
                          </div>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>{t('cancel') || 'Cancel'}</AlertDialogCancel>
                          <AlertDialogAction onClick={() => restoreBackup(backup.backup_id)}>
                            {t('confirm') || 'Confirm'}
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>

                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="outline" size="sm">
                          <IconTrash className="h-4 w-4 text-destructive" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>{t('deleteTitle') || 'Delete Backup'}</AlertDialogTitle>
                          <AlertDialogDescription>
                            {t('deleteWarning') ||
                              'This action cannot be undone. The backup file will be permanently deleted.'}
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>{t('cancel') || 'Cancel'}</AlertDialogCancel>
                          <AlertDialogAction
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                            onClick={() => deleteBackup(backup.backup_id)}
                          >
                            {t('delete') || 'Delete'}
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
