'use client';

/**
 * [INPUT]
 * @/components/features/settings/sections/integration/credentials/* (POS: Credentials sub-panels and state hook)
 *
 * [OUTPUT]
 * CredentialsSection: Vault, file, and OAuth credential management UI.
 *
 * [POS]
 * Settings integration tab for credential upload, vault secrets, and OAuth integrations.
 */

import { memo } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import SettingsSection from '../../SettingsSection';
import { localizeReactNode } from '@/lib/utils/localeText';
import { CredentialsDialogs } from './CredentialsDialogs';
import { CredentialsFilePanel } from './CredentialsFilePanel';
import { CredentialsOAuthPanel } from './CredentialsOAuthPanel';
import { CredentialsVaultPanel } from './CredentialsVaultPanel';
import { useCredentialsSection } from './useCredentialsSection';

const CredentialsSection = memo(() => {
  const t = useTranslations('settings.credentials');
  const locale = useLocale();
  const state = useCredentialsSection();

  return localizeReactNode(
    <SettingsSection title={t('title')} description={t('description')}>
      <input ref={state.fileInputRef} type="file" className="hidden" aria-label="Credential file input" />

      <div className="space-y-6">
        <CredentialsVaultPanel
          isVaultLoading={state.isVaultLoading}
          openVaultCreateModal={state.openVaultCreateModal}
          openVaultEditModal={state.openVaultEditModal}
          setDeleteVaultTarget={state.setDeleteVaultTarget}
          vaultCredentials={state.vaultCredentials}
        />
        <CredentialsFilePanel
          credentials={state.credentials}
          handleUpload={state.handleUpload}
          isLoading={state.isLoading}
          isUploading={state.isUploading}
          missingCredentials={state.missingCredentials}
          setDeleteTarget={state.setDeleteTarget}
          uploadingFilename={state.uploadingFilename}
        />
      </div>

      <CredentialsOAuthPanel
        googleOauthPolling={state.googleOauthPolling}
        googleWorkspaceWriteEnabled={state.googleWorkspaceWriteEnabled}
        handleGoogleWorkspaceConnect={state.handleGoogleWorkspaceConnect}
        isOauthLoading={state.isOauthLoading}
        oauthCreds={state.oauthCreds}
        openConnectModal={state.openConnectModal}
        prepareDisconnect={state.prepareDisconnect}
      />

      <CredentialsDialogs
        clearSyncedMemory={state.clearSyncedMemory}
        closeConnectModal={state.closeConnectModal}
        connectModalTarget={state.connectModalTarget}
        deleteTarget={state.deleteTarget}
        deleteVaultTarget={state.deleteVaultTarget}
        disconnectConfirmTarget={state.disconnectConfirmTarget}
        editingVaultCred={state.editingVaultCred}
        googleOauthConfigured={state.googleOauthConfigured}
        googleOauthPolling={state.googleOauthPolling}
        handleConnectOauth={state.handleConnectOauth}
        handleDeleteConfirm={state.handleDeleteConfirm}
        handleDeleteVaultConfirm={state.handleDeleteVaultConfirm}
        handleDisconnectOauth={state.handleDisconnectOauth}
        handleGoogleWorkspaceConnect={state.handleGoogleWorkspaceConnect}
        handleSaveVaultCredential={state.handleSaveVaultCredential}
        providerTreeCount={state.providerTreeCount}
        scopeInput={state.scopeInput}
        setClearSyncedMemory={state.setClearSyncedMemory}
        setDeleteTarget={state.setDeleteTarget}
        setDeleteVaultTarget={state.setDeleteVaultTarget}
        setDisconnectConfirmTarget={state.setDisconnectConfirmTarget}
        setScopeInput={state.setScopeInput}
        setTokenInput={state.setTokenInput}
        setUserIdInput={state.setUserIdInput}
        setVaultDesc={state.setVaultDesc}
        setVaultLabel={state.setVaultLabel}
        setVaultModalOpen={state.setVaultModalOpen}
        setVaultPassword={state.setVaultPassword}
        setVaultTotp={state.setVaultTotp}
        tokenInput={state.tokenInput}
        userIdInput={state.userIdInput}
        vaultDesc={state.vaultDesc}
        vaultLabel={state.vaultLabel}
        vaultModalOpen={state.vaultModalOpen}
        vaultPassword={state.vaultPassword}
        vaultTotp={state.vaultTotp}
      />
    </SettingsSection>,
    locale,
  );
});

CredentialsSection.displayName = 'CredentialsSection';

export default CredentialsSection;
