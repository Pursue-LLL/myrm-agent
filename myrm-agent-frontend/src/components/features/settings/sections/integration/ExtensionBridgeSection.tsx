'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { PlugZap, AlertCircle } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import SettingsSection from '../SettingsSection';
import ExtensionClipAgentField from './extension/ExtensionClipAgentField';
import {
  ExtensionConnectionInfoCard,
  ExtensionConnectionStatusBar,
  ExtensionSetupGuide,
} from './extension/ExtensionConnectionPanels';
import { ExtensionDomainsPanel, ExtensionTabsPanel } from './extension/ExtensionAccessPanels';
import { useExtensionBridge } from './extension/useExtensionBridge';

const ExtensionBridgeSection = memo(() => {
  const t = useTranslations('settings');
  const {
    wsUrl,
    status,
    setupHints,
    loading,
    fetchError,
    saving,
    domainInput,
    setDomainInput,
    pairingCode,
    pairingLoading,
    fetchStatus,
    handleCreatePairing,
    handleCopyWsUrl,
    handleAddDomain,
    handleRemoveDomain,
    handleAllowAllChange,
    handleToggleTabPause,
    handleDisconnect,
  } = useExtensionBridge();

  return (
    <SettingsSection
      title={
        <span className="flex items-center gap-2">
          <PlugZap className="h-5 w-5 text-primary" />
          {t('extension.title')}
        </span>
      }
      description={t('extension.description')}
    >
      {fetchError && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between p-3 rounded-lg border border-destructive/40 bg-destructive/5">
          <p className="text-sm text-destructive-text flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {t('extension.fetchError')}
          </p>
          <Button variant="outline" size="sm" onClick={fetchStatus}>
            {t('extension.retry')}
          </Button>
        </div>
      )}

      <ExtensionConnectionInfoCard
        wsUrl={wsUrl}
        status={status}
        setupHints={setupHints}
        pairingCode={pairingCode}
        pairingLoading={pairingLoading}
        onCopyWsUrl={handleCopyWsUrl}
        onCreatePairing={handleCreatePairing}
      />

      <ExtensionConnectionStatusBar
        status={status}
        loading={loading}
        onRefresh={fetchStatus}
        onDisconnect={handleDisconnect}
      />

      {!status.connected && <ExtensionSetupGuide />}

      <div className="p-4 rounded-lg border border-border/50 bg-muted/20 space-y-1">
        <h4 className="text-sm font-medium">{t('extension.wikiClipHintTitle')}</h4>
        <p className="text-xs text-muted-foreground">{t('extension.wikiClipHintDescription')}</p>
      </div>

      <ExtensionClipAgentField />

      <ExtensionDomainsPanel
        status={status}
        saving={saving}
        domainInput={domainInput}
        onDomainInputChange={setDomainInput}
        onAddDomain={handleAddDomain}
        onRemoveDomain={handleRemoveDomain}
        onAllowAllChange={handleAllowAllChange}
      />

      <ExtensionTabsPanel status={status} saving={saving} onToggleTabPause={handleToggleTabPause} />
    </SettingsSection>
  );
});

ExtensionBridgeSection.displayName = 'ExtensionBridgeSection';

export default ExtensionBridgeSection;
