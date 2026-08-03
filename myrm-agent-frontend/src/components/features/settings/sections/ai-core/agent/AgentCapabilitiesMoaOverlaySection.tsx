'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { cn } from '@/lib/utils';
import {
  emptyMoaPresetsMap,
  MOA_PRESET_DEFAULT_ID,
  MOA_PRESET_FAST_ID,
  MOA_PRESET_IDS,
  MOA_PRESET_REVIEW_ID,
  type MoaPresetId,
  buildPresetsForMoaEnable,
  presetBlocksFromOverlay,
  resolvePresetReferenceSelections,
} from '@/lib/moaPresetUtils';
import type { AgentCapabilitiesTabProps } from './AgentCapabilitiesTab';
import { ConsensusRefModels } from './AgentCapabilitiesConsensusSection';

type SectionProps = {
  editor: AgentCapabilitiesTabProps['editor'];
  t: ReturnType<typeof useTranslations>;
};

const FANOUT_OPTIONS = [
  { value: 'user_turn', labelKey: 'moaOverlayFanoutUserTurn' },
  { value: 'per_iteration', labelKey: 'moaOverlayFanoutPerIteration' },
  { value: 'every_n', labelKey: 'moaOverlayFanoutEveryN' },
] as const;

const PRIVACY_OPTIONS = [
  { value: 'off', labelKey: 'moaOverlayPrivacyOff' },
  { value: 'display', labelKey: 'moaOverlayPrivacyDisplay' },
  { value: 'full', labelKey: 'moaOverlayPrivacyFull' },
] as const;

const PRESET_TAB_KEYS: Record<MoaPresetId, 'moaOverlayPresetDefaultTab' | 'moaOverlayPresetReviewTab' | 'moaOverlayPresetFastTab'> = {
  [MOA_PRESET_DEFAULT_ID]: 'moaOverlayPresetDefaultTab',
  [MOA_PRESET_REVIEW_ID]: 'moaOverlayPresetReviewTab',
  [MOA_PRESET_FAST_ID]: 'moaOverlayPresetFastTab',
};

function readOverlayPresets(overlay: Record<string, unknown>): Record<MoaPresetId, Record<string, unknown>> {
  const blocks = presetBlocksFromOverlay(overlay);
  const merged = emptyMoaPresetsMap();
  for (const presetId of MOA_PRESET_IDS) {
    if (blocks[presetId]) {
      merged[presetId] = {
        reference_model_selections: resolvePresetReferenceSelections(overlay, presetId),
        ...blocks[presetId],
      };
    }
  }
  const topRefs = overlay.reference_model_selections;
  if (Array.isArray(topRefs) && topRefs.length > 0) {
    const defaultRefs = merged[MOA_PRESET_DEFAULT_ID].reference_model_selections;
    if (defaultRefs.length === 0) {
      merged[MOA_PRESET_DEFAULT_ID] = {
        ...merged[MOA_PRESET_DEFAULT_ID],
        reference_model_selections: topRefs as Array<{ providerId: string; model: string }>,
      };
    }
  }
  return merged;
}

export function MoaOverlaySection({ editor, t }: SectionProps) {
  const ep = editor.engineParams ?? {};
  const overlay = (ep.moa_overlay as Record<string, unknown>) ?? {};
  const isEnabled = !!overlay.enabled;
  const [activePresetTab, setActivePresetTab] = useState<MoaPresetId>(MOA_PRESET_DEFAULT_ID);

  const setOverlay = (patch: Record<string, unknown>) => {
    editor.setEngineParams({ ...ep, moa_overlay: { ...overlay, ...patch } });
  };

  const setPresetRefs = (presetId: MoaPresetId, refs: Array<{ providerId: string; model: string }>) => {
    const presets = readOverlayPresets(overlay);
    presets[presetId] = { ...presets[presetId], reference_model_selections: refs };
    const patch: Record<string, unknown> = { presets };
    if (presetId === MOA_PRESET_DEFAULT_ID) {
      patch.reference_model_selections = refs;
    }
    setOverlay(patch);
  };

  const activePresetConsensus = {
    reference_model_selections: resolvePresetReferenceSelections(overlay, activePresetTab),
  };

  return (
    <div className="rounded-xl bg-card/60 border border-border/50 p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h4 className="text-sm font-medium text-foreground">{t('agent.moaOverlayTitle')}</h4>
          <p className="text-xs text-muted-foreground mt-0.5">{t('agent.moaOverlayDesc')}</p>
        </div>
        <Switch
          checked={isEnabled}
          onCheckedChange={(checked) => {
            if (checked) {
              const presets = buildPresetsForMoaEnable(overlay);
              const defaultRefs = presets[MOA_PRESET_DEFAULT_ID].reference_model_selections;
              setOverlay({
                enabled: true,
                fanout: overlay.fanout ?? 'user_turn',
                every_n: overlay.every_n ?? 2,
                reference_temperature: overlay.reference_temperature ?? 0.6,
                min_successful: overlay.min_successful ?? 1,
                timeout_per_model: overlay.timeout_per_model ?? 120,
                timeout_total: overlay.timeout_total ?? 300,
                reference_max_tokens: overlay.reference_max_tokens ?? 600,
                reference_reasoning_effort: overlay.reference_reasoning_effort ?? 'low',
                privacy_filter: overlay.privacy_filter ?? 'off',
                reference_model_selections:
                  defaultRefs.length > 0
                    ? defaultRefs
                    : ((overlay.reference_model_selections as Array<{ providerId: string; model: string }>) ??
                      []),
                presets,
              });
              return;
            }
            setOverlay({ ...overlay, enabled: false });
          }}
        />
      </div>
      {isEnabled && (
        <>
          <p className="text-[11px] text-muted-foreground">{t('agent.moaOverlayPickerHint')}</p>
          <div className="space-y-4 pt-2 border-t border-border/30">
            <div className="flex flex-wrap gap-1 p-0.5 rounded-lg bg-muted/60">
              {MOA_PRESET_IDS.map((presetId) => (
                <button
                  key={presetId}
                  type="button"
                  onClick={() => setActivePresetTab(presetId)}
                  className={cn(
                    'px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
                    activePresetTab === presetId
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {t(`agent.${PRESET_TAB_KEYS[presetId]}`)}
                </button>
              ))}
            </div>
            <ConsensusRefModels
              consensus={activePresetConsensus}
              setConsensus={(patch) => {
                const refs = patch.reference_model_selections;
                if (Array.isArray(refs)) {
                  setPresetRefs(
                    activePresetTab,
                    refs as Array<{ providerId: string; model: string }>,
                  );
                }
              }}
              t={t}
              noModelsKey="moaOverlayNoModels"
            />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground">
                  {t('agent.moaOverlayFanout')}
                </label>
                <Select
                  value={(overlay.fanout as string) || 'user_turn'}
                  onValueChange={(v) => setOverlay({ fanout: v })}
                >
                  <SelectTrigger className="w-full mt-1 h-9 rounded-lg text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {FANOUT_OPTIONS.map(({ value, labelKey }) => (
                      <SelectItem key={value} value={value}>
                        {t(`agent.${labelKey}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {(overlay.fanout as string) === 'every_n' && (
                <div>
                  <label className="text-xs font-medium text-muted-foreground">
                    {t('agent.moaOverlayEveryN')}
                  </label>
                  <Input
                    type="number"
                    min={1}
                    max={20}
                    value={(overlay.every_n as number) ?? 2}
                    onChange={(e) =>
                      setOverlay({ every_n: Math.max(1, parseInt(e.target.value, 10) || 2) })
                    }
                    className="w-full mt-1"
                  />
                </div>
              )}
              <div>
                <label className="text-xs font-medium text-muted-foreground">
                  {t('agent.moaOverlayPrivacy')}
                </label>
                <Select
                  value={(overlay.privacy_filter as string) || 'off'}
                  onValueChange={(v) => setOverlay({ privacy_filter: v })}
                >
                  <SelectTrigger className="w-full mt-1 h-9 rounded-lg text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PRIVACY_OPTIONS.map(({ value, labelKey }) => (
                      <SelectItem key={value} value={value}>
                        {t(`agent.${labelKey}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
