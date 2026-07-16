'use client';

import { useTranslations } from 'next-intl';
import {
  IconAlertCircle,
  IconCheckCircle,
  IconClock,
  IconTrash,
  IconUpload,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import type { CredentialFile } from '@/services/credentials';
import type { CredentialsSectionState } from './useCredentialsSection';

type CredentialsFilePanelProps = Pick<
  CredentialsSectionState,
  | 'credentials'
  | 'handleUpload'
  | 'isLoading'
  | 'isUploading'
  | 'missingCredentials'
  | 'setDeleteTarget'
  | 'uploadingFilename'
>;

function CredentialExpiryBadge({ cred, t }: { cred: CredentialFile; t: ReturnType<typeof useTranslations> }) {
  if (!cred.expiry_status || cred.expiry_status === 'error') return null;

  if (cred.expiry_status === 'valid') {
    return (
      <Badge variant="outline" className="text-green-600 border-green-600">
        <IconCheckCircle className="h-3 w-3 mr-1" />
        {t('valid')}
      </Badge>
    );
  }

  if (cred.expiry_status === 'expiring_soon') {
    return (
      <Badge variant="outline" className="text-amber-600 border-amber-600">
        <IconClock className="h-3 w-3 mr-1" />
        {t('expiringSoon', { days: String(cred.remaining_days) })}
      </Badge>
    );
  }

  if (cred.expiry_status === 'expired') {
    return (
      <Badge variant="outline" className="text-red-600 border-red-600">
        <IconAlertCircle className="h-3 w-3 mr-1" />
        {t('expired')}
      </Badge>
    );
  }

  return null;
}

export function CredentialsFilePanel({
  credentials,
  handleUpload,
  isLoading,
  isUploading,
  missingCredentials,
  setDeleteTarget,
  uploadingFilename,
}: CredentialsFilePanelProps) {
  const t = useTranslations('settings.credentials');

  return (
    <div className="border-t border-border pt-6">
      <h3 className="font-medium mb-3 flex items-center gap-2">
        <IconCheckCircle className="h-5 w-5 text-green-500" />
        {t('uploadedTitle')} (Files)
        <Badge variant="secondary" className="ml-auto">
          {credentials.length}
        </Badge>
      </h3>

      {missingCredentials.length > 0 && (
        <div className="rounded-lg border border-amber-500/50 bg-amber-500/10 p-4 mb-4">
          <div className="flex items-start gap-3">
            <IconAlertCircle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-medium text-amber-500 mb-2">{t('missingTitle')}</h3>
              <div className="space-y-2">
                {missingCredentials.map((filename) => (
                  <div key={filename} className="flex items-center justify-between p-2 rounded bg-background/50">
                    <span className="text-sm font-mono">{filename}</span>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleUpload(filename)}
                      disabled={isUploading && uploadingFilename === filename}
                    >
                      <IconUpload className="h-4 w-4 mr-2" />
                      {t('upload')}
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((index) => (
            <div key={index} className="flex items-center gap-3 p-3 rounded-lg border">
              <div className="h-10 w-10 rounded bg-muted animate-pulse" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-32 bg-muted animate-pulse rounded" />
                <div className="h-3 w-20 bg-muted animate-pulse rounded" />
              </div>
            </div>
          ))}
        </div>
      ) : credentials.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">{t('noCredentials')}</div>
      ) : (
        <div className="space-y-2">
          {credentials.map((cred) => (
            <div
              key={cred.filename}
              className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors"
            >
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <div className="font-mono text-sm font-medium">{cred.filename}</div>
                  <CredentialExpiryBadge cred={cred} t={t} />
                </div>
                <div className="text-xs text-muted-foreground mt-1">{(cred.size / 1024).toFixed(2)} KB</div>
              </div>

              <Button
                size="sm"
                variant="ghost"
                onClick={() => setDeleteTarget(cred.filename)}
                className="text-red-500 hover:text-red-700 hover:bg-red-500/10"
              >
                <IconTrash className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
