'use client';

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Globe, PlugZap, Trash2, RefreshCw, ExternalLink } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Input } from '@/components/primitives/input';
import { IconCopy, IconCheck } from '@/components/features/icons/PremiumIcons';
import { toast } from '@/hooks/useToast';
import SettingsSection from '../SettingsSection';
import { cn } from '@/lib/utils';
import { getWsUrl } from '@/lib/api';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import {
  getExtensionStatus,
  updateAuthorizedDomains,
  disconnectExtension,
  type ExtensionStatus,
  type ExtensionTab,
} from '@/services/extension';

const EXTENSION_WS_ENDPOINT = '/ws/extension';
const EXTENSION_INSTALL_PATH = '~/.myrm/myrm-agent/myrm-agent-extension';
const EXTENSION_DEV_PATH = 'myrm-agent/myrm-agent-extension';

const ExtensionBridgeSection = memo(() => {
  const t = useTranslations('settings');
  const [status, setStatus] = useState<ExtensionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [domainInput, setDomainInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [copiedWs, setCopiedWs] = useState(false);
  const [copiedInstallPath, setCopiedInstallPath] = useState(false);
  const [copiedDevPath, setCopiedDevPath] = useState(false);

  const wsUrl = useMemo(() => getWsUrl(EXTENSION_WS_ENDPOINT), []);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getExtensionStatus();
      setStatus(data);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const handleCopy = useCallback(async (text: string, setCopied: (value: boolean) => void) => {
    try {
      await writeToClipboard(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast({ title: t('extension.copyFailed'), variant: 'destructive' });
    }
  }, [t]);

  const handleAddDomain = useCallback(async () => {
    const domain = domainInput.trim();
    if (!domain || !status) return;

    const domains = [...status.authorized_domains, domain];
    setSaving(true);
    try {
      const result = await updateAuthorizedDomains(domains);
      setStatus((prev) => prev ? { ...prev, authorized_domains: result.authorized_domains } : prev);
      setDomainInput('');
      toast({ title: t('extension.domainAdded'), variant: 'default' });
    } catch {
      toast({ title: t('extension.saveFailed'), variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  }, [domainInput, status, t]);

  const handleRemoveDomain = useCallback(async (domain: string) => {
    if (!status) return;
    const domains = status.authorized_domains.filter((d) => d !== domain);
    setSaving(true);
    try {
      const result = await updateAuthorizedDomains(domains);
      setStatus((prev) => prev ? { ...prev, authorized_domains: result.authorized_domains } : prev);
    } catch {
      toast({ title: t('extension.saveFailed'), variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  }, [status, t]);

  const handleDisconnect = useCallback(async () => {
    try {
      await disconnectExtension();
      fetchStatus();
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
      {/* Connection Status */}
      <div className="flex items-center justify-between p-4 rounded-lg border border-border/50 bg-background/50">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'w-3 h-3 rounded-full',
              status?.connected ? 'bg-green-500 animate-pulse' : 'bg-muted-foreground/30',
            )}
          />
          <div>
            <p className="text-sm font-medium">
              {status?.connected ? t('extension.connected') : t('extension.notConnected')}
            </p>
            {status?.connected && (
              <p className="text-xs text-muted-foreground">
                {status.browser_name} · v{status.extension_version}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={fetchStatus}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          {status?.connected && (
            <Button variant="destructive" size="sm" onClick={handleDisconnect}>
              {t('extension.disconnect')}
            </Button>
          )}
        </div>
      </div>

      {/* Setup Guide (when not connected) */}
      {!status?.connected && (
        <div className="p-4 rounded-lg border border-dashed border-primary/30 bg-primary/5 space-y-4">
          <h4 className="text-sm font-medium">{t('extension.setupGuide')}</h4>
          <ol className="text-xs text-muted-foreground space-y-1 list-decimal list-inside">
            <li>{t('extension.step1')}</li>
            <li>{t('extension.step2')}</li>
            <li>{t('extension.step3')}</li>
          </ol>

          <div className="space-y-3 pt-1">
            <div className="space-y-2">
              <p className="text-xs font-medium text-foreground">{t('extension.wsUrlLabel')}</p>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <code className="flex-1 break-all rounded-md bg-background/80 px-2 py-1.5 text-xs text-muted-foreground border border-border/60">
                  {wsUrl}
                </code>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="shrink-0"
                  onClick={() => void handleCopy(wsUrl, setCopiedWs)}
                >
                  {copiedWs ? (
                    <IconCheck className="mr-1.5 h-3.5 w-3.5 text-green-500" />
                  ) : (
                    <IconCopy className="mr-1.5 h-3.5 w-3.5" />
                  )}
                  {copiedWs ? t('extension.copied') : t('extension.copy')}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">{t('extension.wsUrlHint')}</p>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium text-foreground">{t('extension.extensionPathLabel')}</p>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <code className="flex-1 break-all rounded-md bg-background/80 px-2 py-1.5 text-xs text-muted-foreground border border-border/60">
                  {EXTENSION_INSTALL_PATH}
                </code>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="shrink-0"
                  onClick={() => void handleCopy(EXTENSION_INSTALL_PATH, setCopiedInstallPath)}
                >
                  {copiedInstallPath ? (
                    <IconCheck className="mr-1.5 h-3.5 w-3.5 text-green-500" />
                  ) : (
                    <IconCopy className="mr-1.5 h-3.5 w-3.5" />
                  )}
                  {copiedInstallPath ? t('extension.copied') : t('extension.copy')}
                </Button>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <code className="flex-1 break-all rounded-md bg-background/80 px-2 py-1.5 text-xs text-muted-foreground border border-border/60">
                  {EXTENSION_DEV_PATH}
                </code>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="shrink-0"
                  onClick={() => void handleCopy(EXTENSION_DEV_PATH, setCopiedDevPath)}
                >
                  {copiedDevPath ? (
                    <IconCheck className="mr-1.5 h-3.5 w-3.5 text-green-500" />
                  ) : (
                    <IconCopy className="mr-1.5 h-3.5 w-3.5" />
                  )}
                  {copiedDevPath ? t('extension.copied') : t('extension.copyDevPath')}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">{t('extension.extensionPathHint')}</p>
            </div>

            {status?.token_required && (
              <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                <p className="text-xs font-medium text-amber-700 dark:text-amber-300">
                  {t('extension.tokenRequiredTitle')}
                </p>
                <p className="text-xs text-muted-foreground mt-1">{t('extension.tokenRequiredHint')}</p>
              </div>
            )}
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
            placeholder="github.com"
            className="flex-1"
            onKeyDown={(e) => e.key === 'Enter' && handleAddDomain()}
          />
          <Button size="sm" onClick={handleAddDomain} disabled={saving || !domainInput.trim()} className="sm:shrink-0">
            {t('extension.addDomain')}
          </Button>
        </div>

        {status?.authorized_domains && status.authorized_domains.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {status.authorized_domains.map((domain) => (
              <Badge key={domain} variant="secondary" className="flex items-center gap-1 px-2 py-1">
                <Globe className="h-3 w-3" />
                {domain}
                <button
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

      {/* Available Tabs (when connected) */}
      {status?.connected && status.available_tabs.length > 0 && (
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
                <span className="text-primary font-mono">{tab.domain}</span>
                <span className="text-muted-foreground truncate flex-1">{tab.title}</span>
                {tab.active && <Badge variant="outline" className="text-[10px]">active</Badge>}
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
