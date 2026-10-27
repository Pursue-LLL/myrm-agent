'use client';

/**
 * [INPUT]
 * - ./TextField::TextField (POS: labelled field)
 * - @/components/primitives/select (POS: provider picker)
 * - @/services/config::BackupSyncConfigValue (POS: the settings being edited)
 *
 * [OUTPUT]
 * - RemoteConnectionFields: provider picker and the connection details of the chosen provider (WebDAV or S3-compatible)
 *
 * [POS]
 * Where the cloud storage is told apart from every other. Passwords and keys never trigger the browser's own
 * password filling: it would put the login of this app into a field meant for the storage.
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import type { BackupSyncConfigValue } from '@/services/config';
import { TextField } from './TextField';

type Edit = (update: (previous: BackupSyncConfigValue) => BackupSyncConfigValue) => void;
type WebdavKey = keyof BackupSyncConfigValue['webdav'];
type S3TextKey = Exclude<keyof BackupSyncConfigValue['s3'], 'forcePathStyle'>;

interface RemoteConnectionFieldsProps {
  config: BackupSyncConfigValue;
  onEdit: Edit;
}

export const RemoteConnectionFields = memo(function RemoteConnectionFields({
  config,
  onEdit,
}: RemoteConnectionFieldsProps) {
  const t = useTranslations('settings.remoteBackup');
  const { webdav, s3 } = config;

  const setWebdav = (key: WebdavKey) => (value: string) =>
    onEdit((previous) => ({ ...previous, webdav: { ...previous.webdav, [key]: value } }));
  const setS3 = (key: S3TextKey) => (value: string) =>
    onEdit((previous) => ({ ...previous, s3: { ...previous.s3, [key]: value } }));

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <p className="text-xs font-semibold text-foreground">{t('provider')}</p>
        <Select
          value={config.provider}
          onValueChange={(provider) =>
            onEdit((previous) => ({ ...previous, provider: provider as BackupSyncConfigValue['provider'] }))
          }
        >
          <SelectTrigger className="w-full text-sm sm:w-64" aria-label={t('provider')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="webdav">{t('webdav')}</SelectItem>
            <SelectItem value="s3">{t('s3')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {config.provider === 'webdav' ? (
        <div className="space-y-4 rounded-xl border border-border/50 bg-muted/30 p-4">
          <TextField
            label={t('webdavHost')}
            placeholder={t('webdavHostPlaceholder')}
            value={webdav.host}
            onChange={setWebdav('host')}
            autoComplete="off"
          />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <TextField
              label={t('webdavUsername')}
              value={webdav.username}
              onChange={setWebdav('username')}
              autoComplete="off"
            />
            <TextField
              label={t('webdavPassword')}
              type="password"
              value={webdav.password}
              onChange={setWebdav('password')}
              autoComplete="new-password"
            />
          </div>
          <TextField label={t('webdavPath')} value={webdav.path} onChange={setWebdav('path')} autoComplete="off" />
        </div>
      ) : (
        <div className="space-y-4 rounded-xl border border-border/50 bg-muted/30 p-4">
          <TextField
            label={t('s3Endpoint')}
            placeholder={t('s3EndpointPlaceholder')}
            value={s3.endpoint}
            onChange={setS3('endpoint')}
            autoComplete="off"
          />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <TextField label={t('s3Region')} value={s3.region} onChange={setS3('region')} autoComplete="off" />
            <TextField label={t('s3Bucket')} value={s3.bucket} onChange={setS3('bucket')} autoComplete="off" />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <TextField
              label={t('s3AccessKeyId')}
              value={s3.accessKeyId}
              onChange={setS3('accessKeyId')}
              autoComplete="off"
            />
            <TextField
              label={t('s3SecretAccessKey')}
              type="password"
              value={s3.secretAccessKey}
              onChange={setS3('secretAccessKey')}
              autoComplete="new-password"
            />
          </div>
          <TextField label={t('s3Prefix')} value={s3.prefix} onChange={setS3('prefix')} autoComplete="off" />
        </div>
      )}
    </div>
  );
});
