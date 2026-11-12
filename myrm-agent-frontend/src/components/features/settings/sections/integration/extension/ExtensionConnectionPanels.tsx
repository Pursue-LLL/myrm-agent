'use client';

/**
 * [INPUT] @/services/extension::ExtensionStatus, ExtensionSetupHints (POS: 扩展状态与配置提示 DTO), ../extensionRelayCapabilityCore (POS: 中继能力矩阵规则)
 * [OUTPUT] ExtensionConnectionInfoCard: 连接信息、配对与中继能力矩阵; ExtensionConnectionStatusBar: 连接状态条; ExtensionSetupGuide: 未连接时的安装指引
 * [POS] ExtensionBridgeSection 的连接区块，纯展示，状态与动作由 useExtensionBridge 提供。
 */

import { memo, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { RefreshCw, Copy } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { toast } from '@/hooks/shared/useToast';
import { buildRelayCapabilityRows, resolveRelayCapabilityStatusKind } from '../extensionRelayCapabilityCore';
import { cn } from '@/lib/utils';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { type ExtensionSetupHints, type ExtensionStatus } from '@/services/extension';

interface ExtensionConnectionInfoCardProps {
  wsUrl: string;
  status: ExtensionStatus;
  setupHints: ExtensionSetupHints;
  pairingCode: string | null;
  pairingLoading: boolean;
  onCopyWsUrl: () => void;
  onCreatePairing: () => void;
}

export const ExtensionConnectionInfoCard = memo(
  ({
    wsUrl,
    status,
    setupHints,
    pairingCode,
    pairingLoading,
    onCopyWsUrl,
    onCreatePairing,
  }: ExtensionConnectionInfoCardProps) => {
    const t = useTranslations('settings');
    const relayCapabilityRows = useMemo(
      () =>
        buildRelayCapabilityRows(status.capabilities).map((cap) => ({
          key: cap.key,
          label: {
            navigate_url: t('extension.relayCapabilityNavigateLabel'),
            list_tabs: t('extension.relayCapabilityListTabsLabel'),
            attach_debugger: t('extension.relayCapabilityAttachLabel'),
            detach_debugger: t('extension.relayCapabilityDetachLabel'),
            agent_tab_control: t('extension.relayCapabilityAgentTabsLabel'),
          }[cap.key],
          available: cap.available,
        })),
      [status.capabilities, t],
    );
    const missingRelayCapabilityLabels = useMemo(
      () => relayCapabilityRows.filter((cap) => !cap.available).map((cap) => cap.label),
      [relayCapabilityRows],
    );
    const relayCapabilityStatus = useMemo(() => {
      const statusKind = resolveRelayCapabilityStatusKind(
        status.connected,
        status.handshake_ready,
        status.capabilities,
      );
      if (statusKind === 'not_connected') {
        return t('extension.notConnected');
      }
      if (statusKind === 'syncing') {
        return t('extension.relayCapabilitySyncing');
      }
      if (statusKind === 'ready') {
        return t('extension.relayCapabilityReady');
      }
      return t('extension.relayCapabilityUpgradeRequired');
    }, [status.capabilities, status.connected, status.handshake_ready, t]);

    return (
      <div className="space-y-3 p-4 rounded-lg border border-border/50 bg-muted/20">
        <h4 className="text-sm font-medium">{t('extension.connectionInfo')}</h4>
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">{t('extension.websocketUrl')}</p>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <code className="text-xs font-mono break-all flex-1 p-2 rounded bg-background border border-border/50">
              {wsUrl}
            </code>
            <Button variant="secondary" size="sm" className="shrink-0" onClick={onCopyWsUrl}>
              <Copy className="h-4 w-4 mr-1" />
              {t('extension.copyUrl')}
            </Button>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          {t('extension.authTokenStatus')}:{' '}
          <span className="text-foreground">
            {setupHints.auth_token_configured
              ? t('extension.authTokenConfigured')
              : setupHints.auth_token_required
                ? t('extension.authTokenRequiredMissing')
                : t('extension.authTokenOptional')}
          </span>
        </p>
        <p className="text-xs text-muted-foreground">
          {t('extension.relayAutomationStatus')}:{' '}
          <span className="text-foreground">
            {setupHints.relay_cdp_ready ? t('extension.relayAutomationReady') : t('extension.relayAutomationNotReady')}
          </span>
        </p>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Button variant="secondary" size="sm" onClick={onCreatePairing} disabled={pairingLoading}>
            {t('extension.createPairingCode')}
          </Button>
          {pairingCode && (
            <code className="text-xs font-mono p-2 rounded bg-background border border-border/50 break-all">
              {pairingCode}
            </code>
          )}
        </div>
        <p className="text-xs text-muted-foreground">{t('extension.pairingHint')}</p>
        <p className="text-xs text-muted-foreground">
          {t('extension.cdpStatus')}:{' '}
          <span className="text-foreground">
            {setupHints.cdp_endpoint_discovered ? t('extension.cdpDetected') : t('extension.cdpNotDetected')}
          </span>
        </p>
        <p className="text-xs text-muted-foreground">
          {t('extension.relayCapabilityStatus')}: <span className="text-foreground">{relayCapabilityStatus}</span>
        </p>
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">{t('extension.relayCapabilityMatrixTitle')}</p>
          <div className="grid gap-1 sm:grid-cols-2">
            {relayCapabilityRows.map((cap) => {
              const pendingHandshake = status.connected && !status.handshake_ready;
              const statusLabel = pendingHandshake
                ? t('extension.relayCapabilitySyncing')
                : cap.available
                  ? t('extension.relayCapabilityAvailable')
                  : t('extension.relayCapabilityUnavailable');
              const statusClass = pendingHandshake
                ? 'text-muted-foreground'
                : cap.available
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-amber-600 dark:text-amber-400';

              return (
                <p key={cap.key} className="text-xs text-muted-foreground">
                  <span className="text-foreground">{cap.label}</span>
                  {' · '}
                  <span className={statusClass}>{statusLabel}</span>
                </p>
              );
            })}
          </div>
        </div>
        {setupHints.auth_token_required && !setupHints.auth_token_configured && (
          <p className="text-xs text-destructive-text">{t('extension.authTokenRequiredHelp')}</p>
        )}
        {status.connected && status.handshake_ready && missingRelayCapabilityLabels.length > 0 && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            {t('extension.relayCapabilityMissingListHelp', { missing: missingRelayCapabilityLabels.join(', ') })}
          </p>
        )}
        {!setupHints.relay_cdp_ready && status.connected && status.handshake_ready && (
          <p className="text-xs text-amber-600 dark:text-amber-400">{t('extension.relayAutomationHelp')}</p>
        )}
        {status.connected && !status.access_policy_valid && (
          <p className="text-xs text-destructive-text">{t('extension.accessPolicyInvalidHelp')}</p>
        )}
        {setupHints.cdp_endpoint_discovered && (
          <p className="text-xs text-amber-600 dark:text-amber-400">{t('extension.cdpRiskHelp')}</p>
        )}
      </div>
    );
  },
);
ExtensionConnectionInfoCard.displayName = 'ExtensionConnectionInfoCard';

interface ExtensionConnectionStatusBarProps {
  status: ExtensionStatus;
  loading: boolean;
  onRefresh: () => void;
  onDisconnect: () => void;
}

export const ExtensionConnectionStatusBar = memo(
  ({ status, loading, onRefresh, onDisconnect }: ExtensionConnectionStatusBarProps) => {
    const t = useTranslations('settings');

    return (
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between p-4 rounded-lg border border-border/50 bg-background/50">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={cn(
              'w-3 h-3 rounded-full shrink-0',
              status.connected ? 'bg-green-500 animate-pulse' : 'bg-muted-foreground/30',
            )}
          />
          <div className="min-w-0">
            <p className="text-sm font-medium">
              {status.connected ? t('extension.connected') : t('extension.notConnected')}
            </p>
            {status.connected && (
              <p className="text-xs text-muted-foreground truncate">
                {status.browser_name} · v{status.extension_version}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="ghost" size="sm" onClick={onRefresh} disabled={loading}>
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
          </Button>
          {status.connected && (
            <Button variant="destructive" size="sm" onClick={onDisconnect}>
              {t('extension.disconnect')}
            </Button>
          )}
        </div>
      </div>
    );
  },
);
ExtensionConnectionStatusBar.displayName = 'ExtensionConnectionStatusBar';

export const ExtensionSetupGuide = memo(() => {
  const t = useTranslations('settings');

  return (
    <div className="p-4 rounded-lg border border-dashed border-primary/30 bg-primary/5 space-y-3">
      <h4 className="text-sm font-medium">{t('extension.setupGuide')}</h4>
      <ol className="text-xs text-muted-foreground space-y-1 list-decimal list-inside">
        <li>{t('extension.step1')}</li>
        <li>{t('extension.step2')}</li>
        <li>{t('extension.step3')}</li>
      </ol>
      <div className="pt-2 border-t border-primary/10">
        <p className="text-xs text-muted-foreground mb-1">{t('extension.extensionPathLabel')}</p>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <code className="text-xs font-mono break-all flex-1 p-2 rounded bg-background border border-border/50">
            ~/.myrm/myrm-agent/myrm-agent-extension
          </code>
          <Button
            variant="secondary"
            size="sm"
            className="shrink-0"
            onClick={async () => {
              const ok = await writeToClipboard('~/.myrm/myrm-agent/myrm-agent-extension', true);
              if (ok) {
                toast({ title: t('extension.copied'), variant: 'default' });
              }
            }}
          >
            <Copy className="h-4 w-4 mr-1" />
            {t('extension.copyUrl')}
          </Button>
        </div>
      </div>
    </div>
  );
});
ExtensionSetupGuide.displayName = 'ExtensionSetupGuide';
