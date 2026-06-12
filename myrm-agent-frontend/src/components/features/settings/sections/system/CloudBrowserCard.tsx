/**
 * [INPUT] services/config::getConfigSyncManager (POS: 配置同步管理器)
 * [INPUT] primitives/select, switch, input, button (POS: Shadcn UI 基础组件)
 * [OUTPUT] CloudBrowserCard: Cloud browser provider configuration card for Settings
 * [POS] 云浏览器服务商配置卡片。支持选择 Provider、输入 API Key、测试连接。
 */

'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { IconGlobe, IconCheck, IconLoader, IconAlertTriangle } from '@/components/features/icons/PremiumIcons';
import { Switch } from '@/components/primitives/switch';
import { Input } from '@/components/primitives/input';
import { Button } from '@/components/primitives/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives/select';
import { getConfigSyncManager, type BrowserCloudProviderConfigValue, type BrowserCloudProviderType } from '@/services/config';
import { toast } from '@/hooks/useToast';

const PROVIDERS: { value: BrowserCloudProviderType; label: string; desc: string }[] = [
  { value: 'browserbase', label: 'Browserbase', desc: 'Managed stealth browsers with residential proxies' },
  { value: 'browserless', label: 'Browserless', desc: 'Scalable headless browser infrastructure' },
  { value: 'notte', label: 'Notte', desc: 'AI-native browser automation platform' },
  { value: 'custom', label: 'Custom', desc: 'Custom WebSocket CDP endpoint' },
];

const DEFAULT_CONFIG: BrowserCloudProviderConfigValue = {
  enabled: false,
  provider: 'browserbase',
  credential: '',
  custom_ws_url: '',
};

type TestStatus = 'idle' | 'testing' | 'success' | 'failed';

const CloudBrowserCard = memo(() => {
  const t = useTranslations('settings.cloudBrowser');
  const [config, setConfig] = useState<BrowserCloudProviderConfigValue>(DEFAULT_CONFIG);
  const [testStatus, setTestStatus] = useState<TestStatus>('idle');
  const [testMessage, setTestMessage] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    try {
      const syncManager = getConfigSyncManager();
      const record = syncManager.get('browserCloudProvider');
      if (record) {
        setConfig({ ...DEFAULT_CONFIG, ...(record as BrowserCloudProviderConfigValue) });
      }
    } catch {
      // Not yet configured
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleSave = useCallback(
    (patch: Partial<BrowserCloudProviderConfigValue>) => {
      const newConfig = { ...config, ...patch };
      setConfig(newConfig);
      setTestStatus('idle');
      try {
        const syncManager = getConfigSyncManager();
        syncManager.set('browserCloudProvider', newConfig);
      } catch {
        toast({ title: t('saveFailed'), variant: 'destructive' });
      }
    },
    [config, t],
  );

  const handleTestConnection = useCallback(async () => {
    setTestStatus('testing');
    setTestMessage('');
    try {
      const resp = await fetch('/api/v1/health/browser/test-cloud-connection', { method: 'POST' });
      const data = await resp.json();
      if (data.status === 'connected') {
        setTestStatus('success');
        setTestMessage(data.message);
      } else {
        setTestStatus('failed');
        setTestMessage(data.message || data.error || 'Connection failed');
      }
    } catch (err) {
      setTestStatus('failed');
      setTestMessage(err instanceof Error ? err.message : 'Network error');
    }
  }, []);

  if (isLoading) return null;

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between px-2">
        <div className="flex items-center gap-3">
          <IconGlobe className="w-5 h-5 text-muted-foreground" />
          <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">
            {t('title')}
          </h2>
        </div>
        <Switch
          checked={config.enabled}
          onCheckedChange={(v) => handleSave({ enabled: v })}
        />
      </div>

      {config.enabled && (
        <div className="rounded-2xl border border-white/5 bg-card/50 p-5 space-y-4">
          {/* Provider Select */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t('provider')}</label>
            <Select
              value={config.provider}
              onValueChange={(v) => handleSave({ provider: v as BrowserCloudProviderType })}
            >
              <SelectTrigger className="w-full bg-background">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROVIDERS.map((p) => (
                  <SelectItem key={p.value} value={p.value}>
                    <div className="flex flex-col py-0.5">
                      <span className="font-medium text-xs">{p.label}</span>
                      <span className="text-[10px] text-muted-foreground">{p.desc}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* API Key / Token */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t('credential')}</label>
            <Input
              type="password"
              placeholder={t('credentialPlaceholder')}
              value={config.credential}
              onChange={(e) => handleSave({ credential: e.target.value })}
              className="bg-background font-mono text-xs"
            />
          </div>

          {/* Custom WS URL (only for custom provider) */}
          {config.provider === 'custom' && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">{t('customWsUrl')}</label>
              <Input
                type="url"
                placeholder="wss://your-cdp-endpoint.example.com"
                value={config.custom_ws_url}
                onChange={(e) => handleSave({ custom_ws_url: e.target.value })}
                className="bg-background font-mono text-xs"
              />
            </div>
          )}

          {/* Test Connection */}
          <div className="flex items-center gap-3 pt-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleTestConnection}
              disabled={testStatus === 'testing' || !config.credential}
              className="gap-2"
            >
              {testStatus === 'testing' && <IconLoader className="w-3.5 h-3.5 animate-spin" />}
              {testStatus === 'success' && <IconCheck className="w-3.5 h-3.5 text-emerald-500" />}
              {testStatus === 'failed' && <IconAlertTriangle className="w-3.5 h-3.5 text-red-500" />}
              {t('testConnection')}
            </Button>
            {testMessage && (
              <span className={`text-xs ${testStatus === 'success' ? 'text-emerald-500' : 'text-red-400'}`}>
                {testMessage}
              </span>
            )}
          </div>
        </div>
      )}
    </section>
  );
});

CloudBrowserCard.displayName = 'CloudBrowserCard';

export default CloudBrowserCard;
