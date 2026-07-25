'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { IconPlus, IconTrash, IconArrowUp, IconArrowDown } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import { getConfigSyncManager, type ComboConfigValue, type ComboTargetValue, type ComboRoutingStrategy } from '@/services/config';

const STRATEGIES: { value: ComboRoutingStrategy; labelKey: string }[] = [
  { value: 'priority', labelKey: 'strategyPriority' },
  { value: 'cost_optimized', labelKey: 'strategyCostOptimized' },
  { value: 'round_robin', labelKey: 'strategyRoundRobin' },
  { value: 'random', labelKey: 'strategyRandom' },
  { value: 'lkgp', labelKey: 'strategyLkgp' },
  { value: 'context_relay', labelKey: 'strategyContextRelay' },
  { value: 'headroom', labelKey: 'strategyHeadroom' },
];

const DEFAULT_COMBO: ComboConfigValue = {
  name: '',
  targets: [],
  strategy: 'priority',
  max_retries: 3,
  retry_on_status: [429, 500, 502, 503, 529],
};

interface ProviderInfo {
  id: string;
  name: string;
  models: string[];
}

function extractProviders(): ProviderInfo[] {
  try {
    const syncManager = getConfigSyncManager();
    const raw = syncManager.get('providers') as Record<string, unknown> | null;
    if (!raw) return [];
    const list = (raw as { providers?: unknown[] }).providers;
    if (!Array.isArray(list)) return [];
    return list
      .filter((p): p is Record<string, unknown> =>
        typeof p === 'object' && p !== null && (Boolean((p as Record<string, unknown>).isEnabled) || Boolean((p as Record<string, unknown>).enabled)),
      )
      .map(p => ({
        id: String(p.id ?? ''),
        name: String(p.name ?? p.id ?? ''),
        models: Array.isArray(p.enabledModels) ? (p.enabledModels as string[]) : [],
      }))
      .filter(p => p.id && p.models.length > 0);
  } catch {
    return [];
  }
}

const ComboEditorCard = memo(() => {
  const t = useTranslations('settings.proxy.combo');
  const [combo, setCombo] = useState<ComboConfigValue>(DEFAULT_COMBO);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);

  useEffect(() => {
    setProviders(extractProviders());
    try {
      const syncManager = getConfigSyncManager();
      const saved = syncManager.get('comboConfig') as ComboConfigValue | null;
      if (saved) setCombo({ ...DEFAULT_COMBO, ...saved });
    } catch { /* first use */ }
  }, []);

  const save = useCallback((updated: ComboConfigValue) => {
    setCombo(updated);
    try {
      const syncManager = getConfigSyncManager();
      syncManager.set('comboConfig', updated);
    } catch { /* silent */ }
  }, []);

  const addTarget = useCallback(() => {
    if (providers.length === 0) return;
    const first = providers[0];
    const target: ComboTargetValue = {
      provider_id: first.id,
      model: first.models[0] ?? '',
      priority: combo.targets.length,
      weight: 1,
      max_requests_per_minute: null,
      enabled: true,
    };
    save({ ...combo, targets: [...combo.targets, target] });
  }, [combo, providers, save]);

  const removeTarget = useCallback((idx: number) => {
    const next = combo.targets.filter((_, i) => i !== idx);
    save({ ...combo, targets: next });
  }, [combo, save]);

  const moveTarget = useCallback((idx: number, dir: -1 | 1) => {
    const arr = [...combo.targets];
    const swapIdx = idx + dir;
    if (swapIdx < 0 || swapIdx >= arr.length) return;
    [arr[idx], arr[swapIdx]] = [arr[swapIdx], arr[idx]];
    save({ ...combo, targets: arr });
  }, [combo, save]);

  const updateTarget = useCallback((idx: number, patch: Partial<ComboTargetValue>) => {
    const arr = [...combo.targets];
    arr[idx] = { ...arr[idx], ...patch };
    save({ ...combo, targets: arr });
  }, [combo, save]);

  const handleStrategyChange = useCallback((val: string) => {
    save({ ...combo, strategy: val as ComboRoutingStrategy });
  }, [combo, save]);

  const handleMaxRetriesChange = useCallback((val: string) => {
    const n = parseInt(val, 10);
    if (n >= 1 && n <= 10) save({ ...combo, max_retries: n });
  }, [combo, save]);

  return (
    <div className="p-4 rounded-lg border border-border/50 bg-muted/30 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium">{t('title')}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">{t('description')}</p>
        </div>
        <Button size="sm" variant="outline" onClick={addTarget} disabled={providers.length === 0}>
          <IconPlus className="h-3.5 w-3.5 mr-1" />
          {t('addTarget')}
        </Button>
      </div>

      {combo.targets.length === 0 && (
        <p className="text-xs text-muted-foreground italic">{t('noTargets')}</p>
      )}

      {combo.targets.map((target, idx) => (
        <div key={`${target.provider_id}-${target.model}-${idx}`} className="flex flex-wrap items-center gap-2 p-3 rounded-md border border-border/30 bg-background">
          <div className="flex flex-col gap-0.5">
            <button
              className="p-0.5 hover:bg-muted rounded disabled:opacity-30"
              onClick={() => moveTarget(idx, -1)}
              disabled={idx === 0}
            >
              <IconArrowUp className="h-3 w-3" />
            </button>
            <button
              className="p-0.5 hover:bg-muted rounded disabled:opacity-30"
              onClick={() => moveTarget(idx, 1)}
              disabled={idx === combo.targets.length - 1}
            >
              <IconArrowDown className="h-3 w-3" />
            </button>
          </div>

          <span className="text-xs text-muted-foreground w-5 text-center font-mono">{idx + 1}</span>

          <Select
            value={target.provider_id}
            onValueChange={val => {
              const prov = providers.find(p => p.id === val);
              updateTarget(idx, { provider_id: val, model: prov?.models[0] ?? '' });
            }}
          >
            <SelectTrigger className="w-32 h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {providers.map(p => (
                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={target.model}
            onValueChange={val => updateTarget(idx, { model: val })}
          >
            <SelectTrigger className="flex-1 h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(providers.find(p => p.id === target.provider_id)?.models ?? []).map(m => (
                <SelectItem key={m} value={m}>{m}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Switch
            checked={target.enabled}
            onCheckedChange={checked => updateTarget(idx, { enabled: checked })}
          />

          <Button size="icon" variant="ghost" className="h-7 w-7 shrink-0" onClick={() => removeTarget(idx)}>
            <IconTrash className="h-3.5 w-3.5 text-destructive" />
          </Button>
        </div>
      ))}

      {combo.targets.length > 0 && (
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">{t('strategy')}</span>
            <Select value={combo.strategy} onValueChange={handleStrategyChange}>
              <SelectTrigger className="w-52 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STRATEGIES.map(s => (
                  <SelectItem key={s.value} value={s.value}>{t(s.labelKey)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">{t('maxRetries')}</span>
            <Select value={String(combo.max_retries)} onValueChange={handleMaxRetriesChange}>
              <SelectTrigger className="w-16 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(n => (
                  <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}
    </div>
  );
});

ComboEditorCard.displayName = 'ComboEditorCard';

export default ComboEditorCard;
