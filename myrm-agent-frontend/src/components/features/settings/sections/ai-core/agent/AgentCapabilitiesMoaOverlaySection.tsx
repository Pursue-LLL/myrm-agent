'use client';

import { useTranslations } from 'next-intl';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
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

export function MoaOverlaySection({ editor, t }: SectionProps) {
  const ep = editor.engineParams ?? {};
  const overlay = (ep.moa_overlay as Record<string, unknown>) ?? {};
  const isEnabled = !!overlay.enabled;

  const setOverlay = (patch: Record<string, unknown>) => {
    editor.setEngineParams({ ...ep, moa_overlay: { ...overlay, ...patch } });
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
            setOverlay(
              checked
                ? {
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
                    reference_model_selections: overlay.reference_model_selections ?? [],
                  }
                : { ...overlay, enabled: false },
            );
          }}
        />
      </div>
      {isEnabled && (
        <div className="space-y-4 pt-2 border-t border-border/30">
          <ConsensusRefModels
            consensus={overlay}
            setConsensus={setOverlay}
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
      )}
    </div>
  );
}
