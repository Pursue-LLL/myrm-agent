/**
 * [INPUT] services/config::getConfigSyncManager (POS: 配置同步管理器)
 * [INPUT] primitives/switch, input, button (POS: Shadcn UI 基础组件)
 * [OUTPUT] BrowserProxyCard: Browser proxy configuration card for Settings
 * [POS] 浏览器代理配置卡片。支持输入代理URL列表、测试连接、加密保存。
 */

'use client';

import { memo, useState, useEffect, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { IconShield, IconCheck, IconLoader, IconAlertTriangle } from '@/components/features/icons/PremiumIcons';
import { Switch } from '@/components/primitives/switch';
import { Button } from '@/components/primitives/button';
import { getConfigSyncManager, type BrowserProxyConfigValue } from '@/services/config';
import { toast } from '@/hooks/useToast';

const DEFAULT_CONFIG: BrowserProxyConfigValue = {
  enabled: false,
  proxies: [],
};

type TestStatus = 'idle' | 'testing' | 'success' | 'failed';

const BrowserProxyCard = memo(() => {
  const t = useTranslations('settings.browserProxy');
  const [config, setConfig] = useState<BrowserProxyConfigValue>(DEFAULT_CONFIG);
  const [proxyText, setProxyText] = useState('');
  const [testStatus, setTestStatus] = useState<TestStatus>('idle');
  const [testMessage, setTestMessage] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    try {
      const syncManager = getConfigSyncManager();
      const record = syncManager.get('browserProxy');
      if (record) {
        const loaded = { ...DEFAULT_CONFIG, ...(record as BrowserProxyConfigValue) };
        setConfig(loaded);
        setProxyText(loaded.proxies.join('\n'));
      }
    } catch {
      // Not yet configured
    } finally {
      setIsLoading(false);
    }
    return () => clearTimeout(debounceRef.current);
  }, []);

  const handleSave = useCallback(
    (patch: Partial<BrowserProxyConfigValue>) => {
      const newConfig = { ...config, ...patch };
      setConfig(newConfig);
      setTestStatus('idle');
      try {
        const syncManager = getConfigSyncManager();
        syncManager.set('browserProxy', newConfig);
      } catch {
        toast({ title: t('saveFailed'), variant: 'destructive' });
      }
    },
    [config, t],
  );

  const handleProxyTextChange = useCallback(
    (text: string) => {
      setProxyText(text);
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        const proxies = text
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean);
        handleSave({ proxies });
      }, 500);
    },
    [handleSave],
  );

  const handleTestConnection = useCallback(async () => {
    setTestStatus('testing');
    setTestMessage('');
    try {
      const resp = await fetch('/api/v1/health/browser/test-proxy-connection', { method: 'POST' });
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
          <IconShield className="w-5 h-5 text-muted-foreground" />
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
          {/* Proxy URL List */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t('proxyUrls')}</label>
            <textarea
              placeholder={t('proxyUrlsPlaceholder')}
              value={proxyText}
              onChange={(e) => handleProxyTextChange(e.target.value)}
              rows={4}
              className="w-full bg-background font-mono text-xs rounded-lg border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 resize-none"
            />
            <p className="text-[10px] text-muted-foreground">{t('proxyUrlsHint')}</p>
          </div>

          {/* Test Connection */}
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleTestConnection}
              disabled={testStatus === 'testing' || config.proxies.length === 0}
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

BrowserProxyCard.displayName = 'BrowserProxyCard';

export default BrowserProxyCard;
