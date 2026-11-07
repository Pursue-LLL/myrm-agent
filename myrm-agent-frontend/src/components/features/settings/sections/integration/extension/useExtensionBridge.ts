/**
 * [INPUT] @/services/extension (POS: 浏览器扩展桥 REST 服务), @/lib/utils/clipboardUtils::writeToClipboard
 * [OUTPUT] useExtensionBridge: 扩展连接状态轮询（5 秒）、配对码、访问策略（域名 / 全部放行 / 标签页暂停）写入与断开连接
 * [POS] ExtensionBridgeSection 的状态与动作层；所有访问策略编辑共用同一次写入、状态合并与失败提示。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import {
  getExtensionStatus,
  getExtensionSetupHints,
  getExtensionWebSocketUrl,
  updateExtensionAccessPolicy,
  disconnectExtension,
  createExtensionPairing,
  buildExtensionPairingBundle,
  type ExtensionAccessPolicy,
  type ExtensionSetupHints,
  type ExtensionStatus,
} from '@/services/extension';

const EMPTY_STATUS: ExtensionStatus = {
  connected: false,
  handshake_ready: false,
  relay_cdp_ready: false,
  extension_version: '',
  browser_name: '',
  authorized_domains: [],
  allow_all_eligible_tabs: false,
  paused_tab_ids: [],
  access_policy_valid: false,
  capabilities: [],
  available_tabs: [],
};

const EMPTY_HINTS: ExtensionSetupHints = {
  auth_token_configured: false,
  auth_token_required: false,
  cdp_endpoint_discovered: false,
  relay_cdp_ready: false,
  access_policy_valid: false,
};

type AccessPolicyUpdate = Parameters<typeof updateExtensionAccessPolicy>[0];

export function useExtensionBridge() {
  const t = useTranslations('settings');
  const wsUrl = useMemo(() => getExtensionWebSocketUrl(), []);
  const [status, setStatus] = useState<ExtensionStatus>(EMPTY_STATUS);
  const [setupHints, setSetupHints] = useState<ExtensionSetupHints>(EMPTY_HINTS);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  const [domainInput, setDomainInput] = useState('');
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [pairingLoading, setPairingLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const fetchStatus = useCallback(async () => {
    let statusOk = false;
    try {
      const data = await getExtensionStatus();
      setStatus(data);
      statusOk = true;
      setFetchError(false);
    } catch {
      setStatus(EMPTY_STATUS);
      setFetchError(true);
    }
    try {
      const hints = await getExtensionSetupHints();
      setSetupHints(hints);
    } catch {
      if (!statusOk) {
        setSetupHints(EMPTY_HINTS);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const handleCreatePairing = useCallback(async () => {
    setPairingLoading(true);
    try {
      const ticket = await createExtensionPairing();
      setPairingCode(ticket.code);
      const bundle = buildExtensionPairingBundle(ticket);
      const ok = await writeToClipboard(bundle, true);
      toast({
        title: ok ? t('extension.pairingCopied') : t('extension.pairingCreated'),
        variant: 'default',
      });
    } catch {
      toast({ title: t('extension.pairingFailed'), variant: 'destructive' });
    } finally {
      setPairingLoading(false);
    }
  }, [t]);

  const handleCopyWsUrl = useCallback(async () => {
    const ok = await writeToClipboard(wsUrl, true);
    if (ok) {
      toast({ title: t('extension.copied'), variant: 'default' });
    }
  }, [wsUrl, t]);

  const notifyWildcardWarning = useCallback(
    (result: ExtensionAccessPolicy) => {
      const wildcardWarning = result.warnings.find((w) => w.code === 'wildcard_includes_root');
      if (wildcardWarning) {
        toast({
          title: t('extension.wildcardWarningTitle'),
          description: t('extension.wildcardIncludesRoot', {
            pattern: wildcardWarning.pattern,
            root: wildcardWarning.root_domain,
          }),
          variant: 'default',
        });
      }
    },
    [t],
  );

  // Every access-policy edit shares the same write, status merge and failure toast; `onSaved` adds the edit-specific follow-up.
  const commitAccessPolicy = useCallback(
    async (policy: AccessPolicyUpdate, onSaved?: (result: ExtensionAccessPolicy) => void | Promise<void>) => {
      setSaving(true);
      try {
        const result = await updateExtensionAccessPolicy(policy);
        setStatus((prev) => ({
          ...prev,
          authorized_domains: result.authorized_domains,
          allow_all_eligible_tabs: result.allow_all_eligible_tabs,
          paused_tab_ids: result.paused_tab_ids,
          access_policy_valid: result.policy_valid,
        }));
        setFetchError(false);
        await onSaved?.(result);
      } catch {
        toast({ title: t('extension.saveFailed'), variant: 'destructive' });
      } finally {
        setSaving(false);
      }
    },
    [t],
  );

  const handleAddDomain = useCallback(async () => {
    const domain = domainInput.trim();
    if (!domain) {
      return;
    }

    await commitAccessPolicy(
      {
        allow_all_eligible_tabs: status.allow_all_eligible_tabs,
        domains: [...status.authorized_domains, domain],
        paused_tab_ids: status.paused_tab_ids,
      },
      (result) => {
        notifyWildcardWarning(result);
        setDomainInput('');
        toast({ title: t('extension.domainAdded'), variant: 'default' });
      },
    );
  }, [
    commitAccessPolicy,
    domainInput,
    notifyWildcardWarning,
    status.authorized_domains,
    status.allow_all_eligible_tabs,
    status.paused_tab_ids,
    t,
  ]);

  const handleRemoveDomain = useCallback(
    (domain: string) =>
      commitAccessPolicy(
        {
          allow_all_eligible_tabs: status.allow_all_eligible_tabs,
          domains: status.authorized_domains.filter((d) => d !== domain),
          paused_tab_ids: status.paused_tab_ids,
        },
        notifyWildcardWarning,
      ),
    [
      commitAccessPolicy,
      notifyWildcardWarning,
      status.authorized_domains,
      status.allow_all_eligible_tabs,
      status.paused_tab_ids,
    ],
  );

  const handleAllowAllChange = useCallback(
    (checked: boolean) =>
      commitAccessPolicy({
        allow_all_eligible_tabs: checked,
        domains: status.authorized_domains,
        paused_tab_ids: status.paused_tab_ids,
      }),
    [commitAccessPolicy, status.authorized_domains, status.paused_tab_ids],
  );

  const handleToggleTabPause = useCallback(
    (tabId: number) => {
      const nextPaused = new Set(status.paused_tab_ids);
      if (nextPaused.has(tabId)) {
        nextPaused.delete(tabId);
      } else {
        nextPaused.add(tabId);
      }
      return commitAccessPolicy(
        {
          allow_all_eligible_tabs: status.allow_all_eligible_tabs,
          domains: status.authorized_domains,
          paused_tab_ids: [...nextPaused],
        },
        fetchStatus,
      );
    },
    [commitAccessPolicy, fetchStatus, status.allow_all_eligible_tabs, status.authorized_domains, status.paused_tab_ids],
  );

  const handleDisconnect = useCallback(async () => {
    try {
      await disconnectExtension();
      await fetchStatus();
      toast({ title: t('extension.disconnected'), variant: 'default' });
    } catch {
      toast({ title: t('extension.disconnectFailed'), variant: 'destructive' });
    }
  }, [fetchStatus, t]);

  return {
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
  };
}
