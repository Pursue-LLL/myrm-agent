'use client';

import { useLocale, useTranslations } from 'next-intl';
import { IconAlertCircle } from '@/components/features/icons/PremiumIcons';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { Button } from '@/components/primitives/button';
import { Checkbox } from '@/components/primitives/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Label } from '@/components/primitives/label';
import { Input } from '@/components/primitives/input';
import type { CredentialsSectionState } from './useCredentialsSection';

type CredentialsDialogsProps = Pick<
  CredentialsSectionState,
  | 'clearSyncedMemory'
  | 'closeConnectModal'
  | 'connectModalTarget'
  | 'deleteTarget'
  | 'deleteVaultTarget'
  | 'disconnectConfirmTarget'
  | 'editingVaultCred'
  | 'googleOauthConfigured'
  | 'googleOauthPolling'
  | 'handleConnectOauth'
  | 'handleDeleteConfirm'
  | 'handleDeleteVaultConfirm'
  | 'handleDisconnectOauth'
  | 'handleGoogleWorkspaceConnect'
  | 'handleSaveVaultCredential'
  | 'providerTreeCount'
  | 'scopeInput'
  | 'setClearSyncedMemory'
  | 'setDeleteTarget'
  | 'setDeleteVaultTarget'
  | 'setDisconnectConfirmTarget'
  | 'setScopeInput'
  | 'setTokenInput'
  | 'setUserIdInput'
  | 'setVaultDesc'
  | 'setVaultLabel'
  | 'setVaultModalOpen'
  | 'setVaultPassword'
  | 'setVaultTotp'
  | 'tokenInput'
  | 'userIdInput'
  | 'vaultDesc'
  | 'vaultLabel'
  | 'vaultModalOpen'
  | 'vaultPassword'
  | 'vaultTotp'
>;

export function CredentialsDialogs({
  clearSyncedMemory,
  closeConnectModal,
  connectModalTarget,
  deleteTarget,
  deleteVaultTarget,
  disconnectConfirmTarget,
  editingVaultCred,
  googleOauthConfigured,
  googleOauthPolling,
  handleConnectOauth,
  handleDeleteConfirm,
  handleDeleteVaultConfirm,
  handleDisconnectOauth,
  handleGoogleWorkspaceConnect,
  handleSaveVaultCredential,
  providerTreeCount,
  scopeInput,
  setClearSyncedMemory,
  setDeleteTarget,
  setDeleteVaultTarget,
  setDisconnectConfirmTarget,
  setScopeInput,
  setTokenInput,
  setUserIdInput,
  setVaultDesc,
  setVaultLabel,
  setVaultModalOpen,
  setVaultPassword,
  setVaultTotp,
  tokenInput,
  userIdInput,
  vaultDesc,
  vaultLabel,
  vaultModalOpen,
  vaultPassword,
  vaultTotp,
}: CredentialsDialogsProps) {
  const t = useTranslations('settings.credentials');
  const locale = useLocale();

  return (
    <>
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={t('deleteConfirmTitle', { defaultValue: 'Delete Credential' })}
        description={t('deleteConfirmDesc', {
          defaultValue: `Are you sure you want to delete "${deleteTarget}"? This action cannot be undone.`,
        })}
        confirmText={t('deleteConfirmBtn', { defaultValue: 'Delete' })}
        cancelText={t('deleteCancel', { defaultValue: 'Cancel' })}
        variant="destructive"
        onConfirm={handleDeleteConfirm}
      />

      <ConfirmDialog
        open={!!deleteVaultTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteVaultTarget(null);
        }}
        title={t('vaultDeleteTitle')}
        description={t('vaultDeleteDesc', { label: deleteVaultTarget ?? '' })}
        confirmText={t('deleteConfirmBtn', { defaultValue: 'Delete' })}
        cancelText={t('deleteCancel', { defaultValue: 'Cancel' })}
        variant="destructive"
        onConfirm={handleDeleteVaultConfirm}
      />

      {vaultModalOpen && (
        <Dialog
          open={vaultModalOpen}
          onOpenChange={(open) => {
            if (!open) setVaultModalOpen(false);
          }}
        >
          <DialogContent className="sm:max-w-md bg-card border border-border">
            <DialogHeader>
              <DialogTitle className="text-foreground">
                {editingVaultCred ? t('vaultEditTitle') : t('vaultAddTitle')}
              </DialogTitle>
              <DialogDescription className="text-muted-foreground">{t('vaultDialogDesc')}</DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="vaultLabel" className="text-foreground">{t('vaultLabelField')}</Label>
                <Input
                  id="vaultLabel"
                  type="text"
                  placeholder={t('vaultLabelPlaceholder')}
                  value={vaultLabel}
                  onChange={(event) => setVaultLabel(event.target.value)}
                  disabled={!!editingVaultCred}
                  className="bg-muted border border-border text-foreground placeholder:text-muted-foreground"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="vaultPassword" className="text-foreground">
                  {editingVaultCred ? t('vaultPasswordKeep') : t('vaultPasswordField')}
                </Label>
                <Input
                  id="vaultPassword"
                  type="password"
                  placeholder={t('vaultPasswordPlaceholder')}
                  value={vaultPassword}
                  onChange={(event) => setVaultPassword(event.target.value)}
                  className="bg-muted border border-border text-foreground placeholder:text-muted-foreground"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="vaultTotp" className="text-foreground">
                  {editingVaultCred ? t('vaultTotpKeep') : t('vaultTotpField')}
                </Label>
                <Input
                  id="vaultTotp"
                  type="password"
                  placeholder={t('vaultTotpPlaceholder')}
                  value={vaultTotp}
                  onChange={(event) => setVaultTotp(event.target.value)}
                  className="bg-muted border border-border text-foreground placeholder:text-muted-foreground"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="vaultDesc" className="text-foreground">{t('vaultDescField')}</Label>
                <Input
                  id="vaultDesc"
                  type="text"
                  placeholder={t('vaultDescPlaceholder')}
                  value={vaultDesc}
                  onChange={(event) => setVaultDesc(event.target.value)}
                  className="bg-muted border border-border text-foreground placeholder:text-muted-foreground"
                />
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setVaultModalOpen(false)}>
                {t('deleteCancel', { defaultValue: 'Cancel' })}
              </Button>
              <Button onClick={() => void handleSaveVaultCredential()}>{t('vaultSave')}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {disconnectConfirmTarget && (
        <Dialog
          open={!!disconnectConfirmTarget}
          onOpenChange={(open) => {
            if (!open) {
              setDisconnectConfirmTarget(null);
              setClearSyncedMemory(false);
            }
          }}
        >
          <DialogContent className="sm:max-w-md bg-card border border-border">
            <DialogHeader>
              <DialogTitle className="text-foreground">
                {t('disconnectConfirmTitle', { name: disconnectConfirmTarget.name })}
              </DialogTitle>
              <DialogDescription className="text-muted-foreground">
                {t('disconnectConfirmDesc', { name: disconnectConfirmTarget.name })}
              </DialogDescription>
            </DialogHeader>

            {providerTreeCount > 0 && (
              <div className="flex items-start gap-3 py-2">
                <Checkbox
                  id="clear-synced-memory"
                  checked={clearSyncedMemory}
                  onCheckedChange={(checked) => setClearSyncedMemory(checked === true)}
                />
                <label
                  htmlFor="clear-synced-memory"
                  className="text-sm leading-relaxed cursor-pointer text-muted-foreground"
                >
                  {locale === 'zh'
                    ? `同时清除已同步的记忆数据（${providerTreeCount} 个数据源）`
                    : `Also remove synced memory data (${providerTreeCount} source${providerTreeCount > 1 ? 's' : ''})`}
                </label>
              </div>
            )}

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setDisconnectConfirmTarget(null);
                  setClearSyncedMemory(false);
                }}
              >
                {t('deleteCancel')}
              </Button>
              <Button variant="destructive" onClick={() => void handleDisconnectOauth()}>
                {t('disconnect')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {connectModalTarget && (
        <Dialog open={!!connectModalTarget} onOpenChange={(open) => { if (!open) closeConnectModal(); }}>
          <DialogContent className="sm:max-w-md bg-card border border-border">
            <DialogHeader>
              <DialogTitle className="text-foreground">
                {t('connectTitle', { name: connectModalTarget.name })}
              </DialogTitle>
              <DialogDescription className="text-muted-foreground">
                {t('connectDesc', { name: connectModalTarget.name })}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              {connectModalTarget.oauthFlow === 'google_workspace' ? (
                <>
                  <p className="text-sm text-muted-foreground leading-relaxed">{t('googleOauthConnectDesc')}</p>
                  {googleOauthConfigured === false && (
                    <div className="flex items-start gap-2.5 p-3 rounded-lg border border-amber-500/30 bg-amber-500/5 text-xs text-amber-700 dark:text-amber-400">
                      <IconAlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                      <span>{t('googleOauthNotConfigured')}</span>
                    </div>
                  )}
                  {googleOauthPolling && (
                    <p className="text-xs text-muted-foreground">{t('googleOauthPolling')}</p>
                  )}
                </>
              ) : (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="token" className="text-foreground">{t('tokenLabel')}</Label>
                    <Input
                      id="token"
                      type="password"
                      placeholder={t('tokenPlaceholder')}
                      value={tokenInput}
                      onChange={(event) => setTokenInput(event.target.value)}
                      className="bg-muted border border-border text-foreground placeholder:text-muted-foreground focus:ring-primary focus:border-primary"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="userId" className="text-foreground">{t('userIdLabel')}</Label>
                    <Input
                      id="userId"
                      type="text"
                      placeholder={t('userIdPlaceholder')}
                      value={userIdInput}
                      onChange={(event) => setUserIdInput(event.target.value)}
                      className="bg-muted border border-border text-foreground placeholder:text-muted-foreground"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="scope" className="text-foreground">{t('scopeLabel')}</Label>
                    <Input
                      id="scope"
                      type="text"
                      placeholder={t('scopePlaceholder')}
                      value={scopeInput}
                      onChange={(event) => setScopeInput(event.target.value)}
                      className="bg-muted border border-border text-foreground placeholder:text-muted-foreground"
                    />
                  </div>
                </>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={closeConnectModal}>
                {t('deleteCancel')}
              </Button>
              {connectModalTarget.oauthFlow === 'google_workspace' ? (
                <Button
                  onClick={() => void handleGoogleWorkspaceConnect('readonly')}
                  disabled={googleOauthPolling || googleOauthConfigured === false}
                >
                  {googleOauthPolling ? t('googleOauthPolling') : t('googleOauthConnectBtn')}
                </Button>
              ) : (
                <Button onClick={() => void handleConnectOauth()}>{t('saveBtn')}</Button>
              )}
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}
