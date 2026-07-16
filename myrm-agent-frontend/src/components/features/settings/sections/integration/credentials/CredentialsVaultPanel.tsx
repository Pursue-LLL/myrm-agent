'use client';

import { useTranslations } from 'next-intl';
import { IconCheckCircle, IconTrash } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import type { CredentialsSectionState } from './useCredentialsSection';

type CredentialsVaultPanelProps = Pick<
  CredentialsSectionState,
  | 'isVaultLoading'
  | 'openVaultCreateModal'
  | 'openVaultEditModal'
  | 'setDeleteVaultTarget'
  | 'vaultCredentials'
>;

export function CredentialsVaultPanel({
  isVaultLoading,
  openVaultCreateModal,
  openVaultEditModal,
  setDeleteVaultTarget,
  vaultCredentials,
}: CredentialsVaultPanelProps) {
  const t = useTranslations('settings.credentials');

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-medium flex items-center gap-2">
          <IconCheckCircle className="h-5 w-5 text-primary" />
          {t('vaultTitle')}
          <Badge variant="secondary" className="ml-auto">
            {vaultCredentials.length}
          </Badge>
        </h3>
        <Button size="sm" onClick={openVaultCreateModal}>
          {t('vaultAdd')}
        </Button>
      </div>
      <p className="text-sm text-muted-foreground mb-4">{t('vaultDescription')}</p>

      {isVaultLoading ? (
        <div className="space-y-2">
          {[1, 2].map((index) => (
            <div key={index} className="flex items-center gap-3 p-3 rounded-lg border">
              <div className="h-10 w-10 rounded bg-muted animate-pulse" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-32 bg-muted animate-pulse rounded" />
                <div className="h-3 w-20 bg-muted animate-pulse rounded" />
              </div>
            </div>
          ))}
        </div>
      ) : vaultCredentials.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground border rounded-lg border-dashed">{t('vaultEmpty')}</div>
      ) : (
        <div className="space-y-2">
          {vaultCredentials.map((cred) => (
            <div
              key={cred.id}
              className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors"
            >
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <div className="font-mono text-sm font-medium">{cred.label}</div>
                  {cred.has_password && <Badge variant="outline" className="text-xs">Password</Badge>}
                  {cred.has_totp_seed && <Badge variant="outline" className="text-xs">TOTP</Badge>}
                </div>
                {cred.description && <div className="text-xs text-muted-foreground mt-1">{cred.description}</div>}
              </div>

              <div className="flex items-center gap-2">
                <Button size="sm" variant="ghost" onClick={() => openVaultEditModal(cred)}>
                  {t('vaultEdit')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setDeleteVaultTarget(cred.label)}
                  className="text-red-500 hover:text-red-700 hover:bg-red-500/10"
                >
                  <IconTrash className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
