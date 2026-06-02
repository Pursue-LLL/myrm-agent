'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { IconRefresh, IconTrash, IconUpload, IconDownload, IconCheck, IconX } from '@/components/ui/icons/PremiumIcons';
import { Cloud } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
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
} from '@/components/ui/alert-dialog';
import { getConfigSyncManager, type BackupSyncConfigValue } from '@/services/config';

interface RemoteBackupFile {
  file_name: string;
  modified_time: string;
  size_bytes: number;
}

const DEFAULT_CONFIG: BackupSyncConfigValue = {
  enabled: false,
  provider: 'webdav',
  autoSync: false,
  syncInterval: 60,
  maxBackups: 10,
  deviceName: '',
  webdav: { host: '', username: '', password: '', path: '/myrm-backups' },
  s3: {
    endpoint: '',
    region: '',
    bucket: '',
    accessKeyId: '',
    secretAccessKey: '',
    prefix: 'myrm-backups/',
    forcePathStyle: true,
  },
};

export default function RemoteBackupSection() {
  const t = useTranslations('settings.remoteBackup');
  const [config, setLocalConfig] = useState<BackupSyncConfigValue>(DEFAULT_CONFIG);
  const [remoteFiles, setRemoteFiles] = useState<RemoteBackupFile[]>([]);
  const [testing, setTesting] = useState(false);
  const [backingUp, setBackingUp] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'idle' | 'success' | 'failed'>('idle');

  useEffect(() => {
    const syncManager = getConfigSyncManager();
    const saved = syncManager.get('backupSync');
    if (saved) {
      const merged = { ...DEFAULT_CONFIG, ...saved };
      setLocalConfig(merged);
      if (merged.enabled && (merged.webdav.host || merged.s3.endpoint)) {
        setTimeout(() => loadRemoteFiles(), 300);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveConfig = useCallback(() => {
    try {
      const syncManager = getConfigSyncManager();
      syncManager.set('backupSync', config);
      toast.success(t('save'));
    } catch {
      toast.error('Failed to save configuration');
    }
  }, [config, t]);

  const buildRequestBody = () => {
    const body: Record<string, unknown> = {
      provider: config.provider,
      device_name: config.deviceName,
      max_backups: config.maxBackups,
    };
    if (config.provider === 'webdav') {
      body.webdav = config.webdav;
    } else {
      body.s3 = {
        endpoint: config.s3.endpoint,
        region: config.s3.region,
        bucket: config.s3.bucket,
        access_key_id: config.s3.accessKeyId,
        secret_access_key: config.s3.secretAccessKey,
        prefix: config.s3.prefix,
        force_path_style: config.s3.forcePathStyle,
      };
    }
    return body;
  };

  const testConnection = async () => {
    setTesting(true);
    setConnectionStatus('idle');
    try {
      const res = await fetch('/api/v1/memory/backup/remote/check-connection', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildRequestBody()),
      });
      const data = await res.json();
      if (data.connected) {
        setConnectionStatus('success');
        toast.success(t('connectionSuccess'));
        loadRemoteFiles();
      } else {
        setConnectionStatus('failed');
        toast.error(t('connectionFailed'));
      }
    } catch {
      setConnectionStatus('failed');
      toast.error(t('connectionFailed'));
    } finally {
      setTesting(false);
    }
  };

  const triggerBackup = async () => {
    setBackingUp(true);
    try {
      const res = await fetch('/api/v1/memory/backup/remote/trigger', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildRequestBody()),
      });
      const data = await res.json();
      if (data.success) {
        toast.success(t('backupSuccess'));
        loadRemoteFiles();
      } else {
        toast.error(data.error || t('backupError'));
      }
    } catch {
      toast.error(t('backupError'));
    } finally {
      setBackingUp(false);
    }
  };

  const loadRemoteFiles = async () => {
    setLoadingFiles(true);
    try {
      const res = await fetch('/api/v1/memory/backup/remote/list', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildRequestBody()),
      });
      const data = await res.json();
      setRemoteFiles(data.files || []);
    } catch {
      setRemoteFiles([]);
    } finally {
      setLoadingFiles(false);
    }
  };

  const restoreFromRemote = async (fileName: string) => {
    try {
      const body = { ...buildRequestBody(), file_name: fileName };
      const res = await fetch('/api/v1/memory/backup/remote/restore', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.success) {
        toast.success(t('restoreSuccess', { count: data.restored_count ?? 0 }));
      } else {
        toast.error(data.error || t('restoreError'));
      }
    } catch {
      toast.error(t('restoreError'));
    }
  };

  const deleteRemoteFile = async (fileName: string) => {
    try {
      const body = { ...buildRequestBody(), file_name: fileName };
      const res = await fetch('/api/v1/memory/backup/remote/delete', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.success) {
        toast.success(t('deleteSuccess'));
        loadRemoteFiles();
      }
    } catch {
      toast.error('Delete failed');
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / k ** i).toFixed(1)} ${sizes[i]}`;
  };

  const updateWebdav = (key: keyof BackupSyncConfigValue['webdav'], value: string) => {
    setLocalConfig((prev) => ({ ...prev, webdav: { ...prev.webdav, [key]: value } }));
  };

  const updateS3 = (key: keyof BackupSyncConfigValue['s3'], value: string | boolean) => {
    setLocalConfig((prev) => ({ ...prev, s3: { ...prev.s3, [key]: value } }));
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cloud className="h-5 w-5" />
            {t('title')}
          </CardTitle>
          <CardDescription>{t('description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex items-center justify-between">
            <Label htmlFor="remote-backup-enabled">{t('enabled')}</Label>
            <Switch
              id="remote-backup-enabled"
              checked={config.enabled}
              onCheckedChange={(checked) => setLocalConfig((prev) => ({ ...prev, enabled: checked }))}
            />
          </div>

          {config.enabled && (
            <>
              <div className="space-y-2">
                <Label>{t('provider')}</Label>
                <Select
                  value={config.provider}
                  onValueChange={(v) => setLocalConfig((prev) => ({ ...prev, provider: v as 'webdav' | 's3' }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="webdav">{t('webdav')}</SelectItem>
                    <SelectItem value="s3">{t('s3')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {config.provider === 'webdav' ? (
                <div className="space-y-3 p-4 border rounded-lg bg-muted/30">
                  <div className="space-y-2">
                    <Label>{t('webdavHost')}</Label>
                    <Input
                      placeholder={t('webdavHostPlaceholder')}
                      value={config.webdav.host}
                      onChange={(e) => updateWebdav('host', e.target.value)}
                    />
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label>{t('webdavUsername')}</Label>
                      <Input
                        value={config.webdav.username}
                        onChange={(e) => updateWebdav('username', e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>{t('webdavPassword')}</Label>
                      <Input
                        type="password"
                        value={config.webdav.password}
                        onChange={(e) => updateWebdav('password', e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label>{t('webdavPath')}</Label>
                    <Input value={config.webdav.path} onChange={(e) => updateWebdav('path', e.target.value)} />
                  </div>
                </div>
              ) : (
                <div className="space-y-3 p-4 border rounded-lg bg-muted/30">
                  <div className="space-y-2">
                    <Label>{t('s3Endpoint')}</Label>
                    <Input
                      placeholder={t('s3EndpointPlaceholder')}
                      value={config.s3.endpoint}
                      onChange={(e) => updateS3('endpoint', e.target.value)}
                    />
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label>{t('s3Region')}</Label>
                      <Input value={config.s3.region} onChange={(e) => updateS3('region', e.target.value)} />
                    </div>
                    <div className="space-y-2">
                      <Label>{t('s3Bucket')}</Label>
                      <Input value={config.s3.bucket} onChange={(e) => updateS3('bucket', e.target.value)} />
                    </div>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label>{t('s3AccessKeyId')}</Label>
                      <Input value={config.s3.accessKeyId} onChange={(e) => updateS3('accessKeyId', e.target.value)} />
                    </div>
                    <div className="space-y-2">
                      <Label>{t('s3SecretAccessKey')}</Label>
                      <Input
                        type="password"
                        value={config.s3.secretAccessKey}
                        onChange={(e) => updateS3('secretAccessKey', e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label>{t('s3Prefix')}</Label>
                    <Input value={config.s3.prefix} onChange={(e) => updateS3('prefix', e.target.value)} />
                  </div>
                </div>
              )}

              <div className="flex items-center justify-between">
                <Label>{t('autoSync')}</Label>
                <Switch
                  checked={config.autoSync}
                  onCheckedChange={(checked) => setLocalConfig((prev) => ({ ...prev, autoSync: checked }))}
                />
              </div>

              {config.autoSync && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label>{t('syncInterval')}</Label>
                    <Input
                      type="number"
                      min={5}
                      max={1440}
                      value={config.syncInterval}
                      onChange={(e) =>
                        setLocalConfig((prev) => ({ ...prev, syncInterval: parseInt(e.target.value) || 60 }))
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>{t('maxBackups')}</Label>
                    <Input
                      type="number"
                      min={1}
                      max={100}
                      value={config.maxBackups}
                      onChange={(e) =>
                        setLocalConfig((prev) => ({ ...prev, maxBackups: parseInt(e.target.value) || 10 }))
                      }
                    />
                  </div>
                </div>
              )}

              <div className="space-y-2">
                <Label>{t('deviceName')}</Label>
                <Input
                  placeholder={t('deviceNamePlaceholder')}
                  value={config.deviceName}
                  onChange={(e) => setLocalConfig((prev) => ({ ...prev, deviceName: e.target.value }))}
                />
              </div>

              <div className="flex flex-wrap gap-2 pt-2">
                <Button variant="outline" onClick={testConnection} disabled={testing}>
                  {connectionStatus === 'success' ? (
                    <IconCheck className="mr-2 h-4 w-4 text-green-500" />
                  ) : connectionStatus === 'failed' ? (
                    <IconX className="mr-2 h-4 w-4 text-red-500" />
                  ) : null}
                  {testing ? t('testing') : t('testConnection')}
                </Button>
                <Button onClick={saveConfig}>{t('save')}</Button>
                <Button variant="secondary" onClick={triggerBackup} disabled={backingUp}>
                  <IconUpload className="mr-2 h-4 w-4" />
                  {backingUp ? t('backingUp') : t('triggerBackup')}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {config.enabled && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>{t('remoteFiles')}</CardTitle>
            </div>
            <Button variant="outline" size="sm" onClick={loadRemoteFiles} disabled={loadingFiles}>
              <IconRefresh className={`h-4 w-4 ${loadingFiles ? 'animate-spin' : ''}`} />
            </Button>
          </CardHeader>
          <CardContent>
            {remoteFiles.length === 0 ? (
              <div className="text-center py-6 text-muted-foreground">{t('noRemoteFiles')}</div>
            ) : (
              <div className="space-y-2">
                {remoteFiles.map((file) => (
                  <div
                    key={file.file_name}
                    className="flex items-center justify-between p-3 border rounded-lg hover:bg-accent/50 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{file.file_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(file.modified_time).toLocaleString()} · {formatBytes(file.size_bytes)}
                      </p>
                    </div>
                    <div className="flex gap-1 ml-2">
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="outline" size="sm">
                            <IconDownload className="h-3.5 w-3.5" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>{t('restoreFromCloud')}</AlertDialogTitle>
                            <AlertDialogDescription>{file.file_name}</AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={() => restoreFromRemote(file.file_name)}>
                              {t('restoreFromCloud')}
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="sm">
                            <IconTrash className="h-3.5 w-3.5 text-destructive" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>{t('deleteFromCloud')}</AlertDialogTitle>
                            <AlertDialogDescription>{file.file_name}</AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={() => deleteRemoteFile(file.file_name)}>
                              {t('deleteFromCloud')}
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
      )}
    </div>
  );
}
