/**
 * Web fetch remote escalation (L4) settings — collapsible block under Search settings.
 */

'use client';

import { memo, useState, useEffect, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronDown } from 'lucide-react';
import { Switch } from '@/components/primitives/switch';
import { Button } from '@/components/primitives/button';
import { IconGlobe, IconLoader } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { getConfigSyncManager, type WebFetchEscalationConfigValue } from '@/services/config';
import { toast } from '@/hooks/useToast';
import { apiRequest } from '@/lib/api';

const DEFAULT_CONFIG: WebFetchEscalationConfigValue = {
  enabled: false,
  jinaApiKey: null,
  firecrawl: {
    inheritFromSearch: true,
    api_key: null,
    apiBase: null,
  },
  sessionCap: 5,
};

const WebFetchEscalationCard = memo(() => {
  const t = useTranslations('settings.webFetchEscalation');
  const [expanded, setExpanded] = useState(false);
  const [config, setConfig] = useState<WebFetchEscalationConfigValue>(DEFAULT_CONFIG);
  const [jinaKeyText, setJinaKeyText] = useState('');
  const [firecrawlKeyText, setFirecrawlKeyText] = useState('');
  const [firecrawlBaseText, setFirecrawlBaseText] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [verifying, setVerifying] = useState<'jina' | 'firecrawl' | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    try {
      const syncManager = getConfigSyncManager();
      const record = syncManager.get('webFetchEscalation');
      if (record) {
        const loaded: WebFetchEscalationConfigValue = {
          ...DEFAULT_CONFIG,
          ...(record as WebFetchEscalationConfigValue),
          firecrawl: {
            ...DEFAULT_CONFIG.firecrawl,
            ...(record as WebFetchEscalationConfigValue).firecrawl,
          },
        };
        setConfig(loaded);
        setJinaKeyText(loaded.jinaApiKey ?? '');
        setFirecrawlKeyText(loaded.firecrawl.api_key ?? '');
        setFirecrawlBaseText(loaded.firecrawl.apiBase ?? '');
      }
    } catch {
      // Not yet configured
    } finally {
      setIsLoading(false);
    }
    return () => clearTimeout(debounceRef.current);
  }, []);

  const persist = useCallback(
    (patch: Partial<WebFetchEscalationConfigValue>) => {
      const newConfig: WebFetchEscalationConfigValue = {
        ...config,
        ...patch,
        firecrawl: patch.firecrawl ? { ...config.firecrawl, ...patch.firecrawl } : config.firecrawl,
      };
      setConfig(newConfig);
      try {
        const syncManager = getConfigSyncManager();
        syncManager.set('webFetchEscalation', {
          enabled: newConfig.enabled,
          jinaApiKey: newConfig.jinaApiKey,
          firecrawl: {
            inheritFromSearch: newConfig.firecrawl.inheritFromSearch,
            api_key: newConfig.firecrawl.api_key,
            apiBase: newConfig.firecrawl.apiBase,
          },
          sessionCap: newConfig.sessionCap,
        });
      } catch {
        toast({ title: t('saveFailed'), variant: 'destructive' });
      }
    },
    [config, t],
  );

  const debouncedKeySave = useCallback(
    (field: 'jina' | 'firecrawl', value: string) => {
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        if (field === 'jina') {
          persist({ jinaApiKey: value.trim() || null });
        } else {
          persist({ firecrawl: { ...config.firecrawl, api_key: value.trim() || null } });
        }
      }, 500);
    },
    [config.firecrawl, persist],
  );

  const handleVerify = async (provider: 'jina' | 'firecrawl') => {
    setVerifying(provider);
    try {
      const apiKey =
        provider === 'jina'
          ? jinaKeyText.trim() || null
          : firecrawlKeyText.trim() || null;
      await apiRequest('/integrations/web-fetch/verify', {
        method: 'POST',
        body: JSON.stringify({
          provider,
          api_key: apiKey,
          inherit_from_search: provider === 'firecrawl' && config.firecrawl.inheritFromSearch,
          api_base: provider === 'firecrawl' ? config.firecrawl.apiBase : null,
        }),
      });
      toast({ title: t('verifySuccess', { provider: provider.toUpperCase() }) });
    } catch (err) {
      toast({
        title: t('verifyFailed'),
        description: err instanceof Error ? err.message : undefined,
        variant: 'destructive',
      });
    } finally {
      setVerifying(null);
    }
  };

  if (isLoading) return null;

  return (
    <section className="rounded-2xl border border-border/60 bg-card/40 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left hover:bg-muted/30 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          <IconGlobe className="h-5 w-5 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-foreground">{t('title')}</h3>
            <p className="text-xs text-muted-foreground truncate">{t('subtitle')}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <Switch
            checked={config.enabled}
            onCheckedChange={(v) => persist({ enabled: v })}
            onClick={(e) => e.stopPropagation()}
          />
          <ChevronDown
            className={cn('h-4 w-4 text-muted-foreground transition-transform', expanded && 'rotate-180')}
          />
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border/50 px-5 py-4 space-y-4">
          <p className="text-xs leading-relaxed text-muted-foreground">{t('description')}</p>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t('jinaApiKey')}</label>
            <input
              type="password"
              placeholder={t('jinaApiKeyPlaceholder')}
              value={jinaKeyText}
              onChange={(e) => {
                setJinaKeyText(e.target.value);
                debouncedKeySave('jina', e.target.value);
              }}
              className="w-full bg-background font-mono text-xs rounded-lg border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
            <p className="text-[10px] text-muted-foreground">{t('jinaApiKeyHint')}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={verifying === 'jina'}
              onClick={() => void handleVerify('jina')}
              className="mt-1"
            >
              {verifying === 'jina' ? <IconLoader className="h-3 w-3 animate-spin" /> : null}
              {t('verifyJina')}
            </Button>
          </div>

          <div className="space-y-2 rounded-xl border border-border/40 p-3">
            <p className="text-[10px] text-muted-foreground">{t('firecrawlKeylessHint')}</p>
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-medium text-muted-foreground">{t('firecrawlInherit')}</span>
              <Switch
                checked={config.firecrawl.inheritFromSearch}
                onCheckedChange={(v) => persist({ firecrawl: { ...config.firecrawl, inheritFromSearch: v } })}
              />
            </div>
            {!config.firecrawl.inheritFromSearch && (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{t('firecrawlApiKey')}</label>
                <input
                  type="password"
                  placeholder={t('firecrawlApiKeyPlaceholder')}
                  value={firecrawlKeyText}
                  onChange={(e) => {
                    setFirecrawlKeyText(e.target.value);
                    debouncedKeySave('firecrawl', e.target.value);
                  }}
                  className="w-full bg-background font-mono text-xs rounded-lg border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                />
              </div>
            )}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">{t('firecrawlApiBase')}</label>
              <input
                type="text"
                placeholder="https://api.firecrawl.dev"
                value={firecrawlBaseText}
                onChange={(e) => {
                  setFirecrawlBaseText(e.target.value);
                  clearTimeout(debounceRef.current);
                  debounceRef.current = setTimeout(() => {
                    persist({ firecrawl: { ...config.firecrawl, apiBase: e.target.value.trim() || null } });
                  }, 500);
                }}
                className="w-full bg-background font-mono text-xs rounded-lg border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
              <p className="text-[10px] text-muted-foreground">{t('firecrawlApiBaseHint')}</p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={verifying === 'firecrawl'}
              onClick={() => void handleVerify('firecrawl')}
            >
              {verifying === 'firecrawl' ? <IconLoader className="h-3 w-3 animate-spin" /> : null}
              {t('verifyFirecrawl')}
            </Button>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t('sessionCap')}</label>
            <input
              type="number"
              min={1}
              max={50}
              value={config.sessionCap}
              onChange={(e) => {
                const parsed = Number.parseInt(e.target.value, 10);
                if (!Number.isNaN(parsed)) {
                  persist({ sessionCap: Math.min(50, Math.max(1, parsed)) });
                }
              }}
              className="w-24 bg-background text-xs rounded-lg border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
            <p className="text-[10px] text-muted-foreground">{t('sessionCapHint')}</p>
          </div>
        </div>
      )}
    </section>
  );
});

WebFetchEscalationCard.displayName = 'WebFetchEscalationCard';

export default WebFetchEscalationCard;
