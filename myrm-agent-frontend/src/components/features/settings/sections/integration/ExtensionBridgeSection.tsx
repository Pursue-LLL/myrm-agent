'use client';

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Globe, PlugZap, Trash2, RefreshCw, ExternalLink, Copy, AlertCircle } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Input } from '@/components/primitives/input';
import { toast } from '@/hooks/useToast';
import SettingsSection from '../SettingsSection';
import { cn } from '@/lib/utils';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import {
  getExtensionStatus,
  getExtensionSetupHints,
  getExtensionWebSocketUrl,
  updateAuthorizedDomains,
  disconnectExtension,
  type ExtensionStatus,
  type ExtensionTab,
} from '@/services/extension';

const EMPTY_STATUS: ExtensionStatus = {
  connected: false,
  extension_version: '',
  browser_name: '',
  authorized_domains: [],
  available_tabs: [],
};

const ExtensionBridgeSection = memo(() => {
  const t = useTranslations('settings');
  const wsUrl = useMemo(() => getExtensionWebSocketUrl(), []);
  const [status, setStatus] = useState<ExtensionStatus>(EMPTY_STATUS);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  const [authTokenConfigured, setAuthTokenConfigured] = useState(false);
  const [domainInput, setDomainInput] = useState('');
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
      setAuthTokenConfigured(hints.auth_token_configured);
    } catch {
      if (!statusOk) {
        setAuthTokenConfigured(false);
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

  const handleCopyWsUrl = useCallback(async () => {
    const ok = await writeToClipboard(wsUrl, true);
    if (ok) {
      toast({ title: t('extension.copied'), variant: 'default' });
    }
  }, [wsUrl, t]);

  const handleAddDomain = useCallback(async () => {
    const domain = domainInput.trim();
    if (!domain) return;

    const domains = [...status.authorized_domains, domain];
    setSaving(true);
    try {
      const result = await updateAuthorizedDomains(domains);
      setStatus((prev) => ({ ...prev, authorized_domains: result.authorized_domains }));
      setFetchError(false);
      setDomainInput('');
      toast({ title: t('extension.domainAdded'), variant: 'default' });
    } catch {
      toast({ title: t('extension.saveFailed'), variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  }, [domainInput, status.authorized_domains, t]);

  const handleRemoveDomain = useCallback(async (domain: string) => {
    const domains = status.authorized_domains.filter((d) => d !== domain);
    setSaving(true);
    try {
      const result = await updateAuthorizedDomains(domains);
      setStatus((prev) => ({ ...prev, authorized_domains: result.authorized_domains }));
      setFetchError(false);
    } catch {
      toast({ title: t('extension.saveFailed'), variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  }, [status.authorized_domains, t]);

  const handleDisconnect = useCallback(async () => {
    try {
      await disconnectExtension();
      await fetchStatus();
      toast({ title: t('extension.disconnected'), variant: 'default' });
    } catch {
      toast({ title: t('extension.disconnectFailed'), variant: 'destructive' });
    }
  }, [fetchStatus, t]);

  if (loading) {
    return (
      <SettingsSection title={t('extension.title')}>
        <div className="animate-pulse h-20 bg-muted/50 rounded-lg" />
      </SettingsSection>
    );
  }

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
          <p className="text-sm text-destructive flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {t('extension.fetchError')}
          </p>
          <Button variant="outline" size="sm" onClick={fetchStatus}>
            {t('extension.retry')}
          </Button>
        </div>
      )}

      {/* Connection Info */}
      <div className="space-y-3 p-4 rounded-lg border border-border/50 bg-muted/20">
        <h4 className="text-sm font-medium">{t('extension.connectionInfo')}</h4>
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">{t('extension.websocketUrl')}</p>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <code className="text-xs font-mono break-all flex-1 p-2 rounded bg-background border border-border/50">
              {wsUrl}
            </code>
            <Button variant="secondary" size="sm" className="shrink-0" onClick={handleCopyWsUrl}>
              <Copy className="h-4 w-4 mr-1" />
              {t('extension.copyUrl')}
            </Button>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          {t('extension.authTokenStatus')}:{' '}
          <span className="text-foreground">
            {authTokenConfigured
              ? t('extension.authTokenConfigured')
              : t('extension.authTokenOptional')}
          </span>
        </p>
      </div>

      {/* Connection Status */}
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
          <Button variant="ghost" size="sm" onClick={fetchStatus}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          {status.connected && (
            <Button variant="destructive" size="sm" onClick={handleDisconnect}>
              {t('extension.disconnect')}
            </Button>
          )}
        </div>
      </div>

      {!status.connected && (
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
                  if (ok) toast({ title: t('extension.copied'), variant: 'default' });
                }}
              >
                <Copy className="h-4 w-4 mr-1" />
                {t('extension.copyUrl')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Authorized Domains */}
      <div className="space-y-3">
        <h4 className="text-sm font-medium flex items-center gap-2">
          <Globe className="h-4 w-4" />
          {t('extension.authorizedDomains')}
        </h4>
        <p className="text-xs text-muted-foreground">{t('extension.domainsHint')}</p>

        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            value={domainInput}
            onChange={(e) => setDomainInput(e.target.value)}
            placeholder={t('extension.domainPlaceholder')}
            className="flex-1 min-w-0"
            onKeyDown={(e) => e.key === 'Enter' && handleAddDomain()}
          />
          <Button size="sm" onClick={handleAddDomain} disabled={saving || !domainInput.trim()}>
            {t('extension.addDomain')}
          </Button>
        </div>

        {status.authorized_domains.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {status.authorized_domains.map((domain) => (
              <Badge key={domain} variant="secondary" className="flex items-center gap-1 px-2 py-1">
                <Globe className="h-3 w-3" />
                {domain}
                <button
                  type="button"
                  onClick={() => handleRemoveDomain(domain)}
                  className="ml-1 hover:text-destructive transition-colors"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}
      </div>

      {status.connected && status.available_tabs.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium flex items-center gap-2">
            <ExternalLink className="h-4 w-4" />
            {t('extension.availableTabs')}
          </h4>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {status.available_tabs.map((tab: ExtensionTab) => (
              <div
                key={tab.tab_id}
                className="flex items-center gap-2 text-xs p-2 rounded bg-muted/30"
              >
                <span className="text-primary font-mono shrink-0">{tab.domain}</span>
                <span className="text-muted-foreground truncate flex-1">{tab.title}</span>
                {tab.active && (
                  <Badge variant="outline" className="text-[10px] shrink-0">
                    {t('extension.tabActive')}
                  </Badge>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </SettingsSection>
  );
});

ExtensionBridgeSection.displayName = 'ExtensionBridgeSection';

export default ExtensionBridgeSection;
