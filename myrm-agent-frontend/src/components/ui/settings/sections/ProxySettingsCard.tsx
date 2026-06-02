'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Switch } from '@/components/ui/switch';
import { IconGlobe, IconShieldAlert } from '@/components/ui/icons/PremiumIcons';
import { BACKEND_BASE_URL } from '@/lib/api';
import { getConfigSyncManager, type ProxySettingsConfigValue } from '@/services/config';
import { toast } from '@/hooks/useToast';
import SettingsSection from './SettingsSection';

const DEFAULT_PROXY_SETTINGS: ProxySettingsConfigValue = {
  enabled: false,
  auth: { allow_any_key: false },
};

const ProxySettingsCard = memo(() => {
  const t = useTranslations('settings.proxy');
  const [settings, setSettings] = useState<ProxySettingsConfigValue>(DEFAULT_PROXY_SETTINGS);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const syncManager = getConfigSyncManager();
        const record = syncManager.get('proxySettings');
        if (record) {
          setSettings({
            ...DEFAULT_PROXY_SETTINGS,
            ...(record as ProxySettingsConfigValue),
          });
        }
      } catch {
        // Config not yet saved — use defaults
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  const handleUpdate = useCallback(
    (patch: Partial<ProxySettingsConfigValue>) => {
      const newSettings = { ...settings, ...patch };
      setSettings(newSettings);
      try {
        const syncManager = getConfigSyncManager();
        syncManager.set('proxySettings', newSettings);
      } catch {
        toast({ title: t('saveFailed'), variant: 'destructive' });
      }
    },
    [settings],
  );

  const handleToggleEnabled = useCallback((checked: boolean) => handleUpdate({ enabled: checked }), [handleUpdate]);

  const handleToggleOpenAuth = useCallback(
    (checked: boolean) => handleUpdate({ auth: { ...settings.auth, allow_any_key: checked } }),
    [handleUpdate, settings.auth],
  );

  const apiEndpoint = `${BACKEND_BASE_URL}/v1`;

  if (isLoading) {
    return <div className="animate-pulse h-32 rounded-2xl bg-secondary/30" />;
  }

  return (
    <SettingsSection
      title={
        <span className="flex items-center gap-2">
          <IconGlobe className="h-5 w-5" />
          {t('title')}
        </span>
      }
      description={t('description')}
      action={<Switch checked={settings.enabled} onCheckedChange={handleToggleEnabled} />}
    >
      {settings.enabled && (
        <div className="space-y-4">
          {/* Endpoint display */}
          <div className="p-4 rounded-lg border border-border/50 bg-muted/30">
            <h3 className="text-sm font-medium mb-1">{t('passthroughEndpoint')}</h3>
            <p className="text-xs text-muted-foreground mb-2">{t('passthroughEndpointDesc')}</p>
            <code className="block p-2 rounded bg-background text-xs font-mono break-all select-all">
              {apiEndpoint}
            </code>
          </div>

          {/* Tool config examples */}
          <div className="p-4 rounded-lg border border-border/50 bg-muted/30">
            <h3 className="text-sm font-medium mb-2">{t('toolConfigTitle')}</h3>
            <pre className="p-3 rounded bg-background text-xs font-mono overflow-x-auto whitespace-pre">
              {`# Aider
export OPENAI_API_BASE=${apiEndpoint}
export OPENAI_API_KEY=sk-myrm-...

# Cline / Continue
{
  "apiProvider": "openai-compatible",
  "apiBaseUrl": "${apiEndpoint}",
  "apiKey": "sk-myrm-..."
}`}
            </pre>
          </div>

          {/* Open auth toggle */}
          <div className="flex items-center justify-between p-4 rounded-lg border border-border/50 bg-muted/30">
            <div className="flex items-start gap-3">
              <IconShieldAlert className="h-5 w-5 text-yellow-500 mt-0.5 shrink-0" />
              <div>
                <h3 className="text-sm font-medium">{t('openAuth')}</h3>
                <p className="text-xs text-muted-foreground mt-0.5">{t('openAuthDesc')}</p>
              </div>
            </div>
            <Switch checked={settings.auth.allow_any_key} onCheckedChange={handleToggleOpenAuth} />
          </div>

          {settings.auth.allow_any_key && (
            <div className="px-4 py-3 rounded-lg border border-yellow-500/30 bg-yellow-50/50 dark:bg-yellow-900/10">
              <p className="text-xs text-yellow-700 dark:text-yellow-400">{t('openAuthWarning')}</p>
            </div>
          )}
        </div>
      )}
    </SettingsSection>
  );
});

ProxySettingsCard.displayName = 'ProxySettingsCard';

export default ProxySettingsCard;
