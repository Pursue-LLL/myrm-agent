/**
 * [INPUT] services/config::getConfigSyncManager (POS: 配置同步管理器)
 * [INPUT] primitives/switch, input (POS: Shadcn UI 基础组件)
 * [OUTPUT] CaptchaSolverCard: CAPTCHA auto-solver configuration card for Settings
 * [POS] CAPTCHA 自动解决配置卡片。支持启用/禁用和 API Key 输入。
 */

'use client';

import { memo, useState, useEffect, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { IconShield } from '@/components/features/icons/PremiumIcons';
import { Switch } from '@/components/primitives/switch';
import { getConfigSyncManager, type CaptchaSolverConfigValue } from '@/services/config';
import { toast } from '@/hooks/useToast';

const DEFAULT_CONFIG: CaptchaSolverConfigValue = {
  enabled: false,
  api_key: '',
};

const CaptchaSolverCard = memo(() => {
  const t = useTranslations('settings.captchaSolver');
  const [config, setConfig] = useState<CaptchaSolverConfigValue>(DEFAULT_CONFIG);
  const [apiKeyText, setApiKeyText] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    try {
      const syncManager = getConfigSyncManager();
      const record = syncManager.get('captchaSolverConfig');
      if (record) {
        const loaded = { ...DEFAULT_CONFIG, ...(record as CaptchaSolverConfigValue) };
        setConfig(loaded);
        setApiKeyText(loaded.api_key);
      }
    } catch {
      // Not yet configured
    } finally {
      setIsLoading(false);
    }
    return () => clearTimeout(debounceRef.current);
  }, []);

  const handleSave = useCallback(
    (patch: Partial<CaptchaSolverConfigValue>) => {
      const newConfig = { ...config, ...patch };
      setConfig(newConfig);
      try {
        const syncManager = getConfigSyncManager();
        syncManager.set('captchaSolverConfig', newConfig);
      } catch {
        toast({ title: t('saveFailed'), variant: 'destructive' });
      }
    },
    [config, t],
  );

  const handleApiKeyChange = useCallback(
    (text: string) => {
      setApiKeyText(text);
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        handleSave({ api_key: text });
      }, 500);
    },
    [handleSave],
  );

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
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t('apiKey')}</label>
            <input
              type="password"
              placeholder={t('apiKeyPlaceholder')}
              value={apiKeyText}
              onChange={(e) => handleApiKeyChange(e.target.value)}
              className="w-full bg-background font-mono text-xs rounded-lg border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
            <p className="text-[10px] text-muted-foreground">{t('apiKeyHint')}</p>
          </div>
        </div>
      )}
    </section>
  );
});

CaptchaSolverCard.displayName = 'CaptchaSolverCard';

export default CaptchaSolverCard;
