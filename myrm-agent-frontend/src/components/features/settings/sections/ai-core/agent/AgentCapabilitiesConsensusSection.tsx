'use client';

import { X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import ProviderIcon from '@/components/features/settings/model-service/ProviderIcon';
import ModelPickerPopover from '@/components/features/app-shell/model-picker-popover';
import type { AgentCapabilitiesTabProps } from './AgentCapabilitiesTab';

type SectionProps = {
  editor: AgentCapabilitiesTabProps['editor'];
  t: ReturnType<typeof useTranslations>;
};

export function ConsensusSection({ editor, t }: SectionProps) {
  const ep = editor.engineParams ?? {};
  const consensus = (ep.consensus as Record<string, unknown>) ?? {};
  const isEnabled = !!consensus.enabled;

  const setConsensus = (patch: Record<string, unknown>) => {
    editor.setEngineParams({ ...ep, consensus: { ...consensus, ...patch } });
  };

  return (
    <div className="rounded-xl bg-card/60 border border-border/50 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-medium text-foreground">{t('agent.consensusTitle')}</h4>
          <p className="text-xs text-muted-foreground mt-0.5">{t('agent.consensusDesc')}</p>
        </div>
        <Switch
          checked={isEnabled}
          onCheckedChange={(checked) => {
            setConsensus(checked ? {
              enabled: true,
              reference_temperature: consensus.reference_temperature ?? 0.6,
              aggregator_temperature: consensus.aggregator_temperature ?? 0.4,
              min_successful: consensus.min_successful ?? 1,
              timeout_per_model: consensus.timeout_per_model ?? 120,
              timeout_total: consensus.timeout_total ?? 300,
              reference_max_tokens: consensus.reference_max_tokens ?? null,
              reference_model_selections: consensus.reference_model_selections ?? [],
              aggregator_model_selection: consensus.aggregator_model_selection ?? null,
            } : { ...consensus, enabled: false });
          }}
        />
      </div>
      {isEnabled && (
        <div className="space-y-4 pt-2 border-t border-border/30">
          <ConsensusRefModels consensus={consensus} setConsensus={setConsensus} t={t} />
          <ConsensusAggModel consensus={consensus} setConsensus={setConsensus} t={t} />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {[
              { key: 'reference_temperature', label: 'consensusRefTemp', def: 0.6, min: 0, max: 2, step: 0.1 },
              { key: 'aggregator_temperature', label: 'consensusAggTemp', def: 0.4, min: 0, max: 2, step: 0.1 },
            ].map(({ key, label, def, min, max, step }) => (
              <div key={key}>
                <label className="text-xs font-medium text-muted-foreground">{t(`agent.${label}`)}</label>
                <Input
                  type="number" min={min} max={max} step={step}
                  value={(consensus[key] as number) ?? def}
                  onChange={(e) => setConsensus({ [key]: parseFloat(e.target.value) || def })}
                  className="w-full mt-1"
                />
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('agent.consensusMinSuccessful')}</label>
              <Input type="number" min={1} max={10} value={(consensus.min_successful as number) ?? 1}
                onChange={(e) => setConsensus({ min_successful: parseInt(e.target.value, 10) || 1 })} className="w-full mt-1" />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('agent.consensusTimeout')}</label>
              <Input type="number" min={10} max={600} value={(consensus.timeout_total as number) ?? 300}
                onChange={(e) => setConsensus({ timeout_total: parseInt(e.target.value, 10) || 300 })} className="w-full mt-1" />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('agent.consensusRefMaxTokens')}</label>
              <p className="text-[10px] text-muted-foreground/60 mt-0.5">{t('agent.consensusRefMaxTokensHint')}</p>
              <Input type="number" min={0} max={16000} step={100}
                placeholder="600"
                value={(consensus.reference_max_tokens as number) || ''}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10);
                  setConsensus({ reference_max_tokens: v > 0 ? v : null });
                }} className="w-full mt-1" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function ConsensusRefModels({ consensus, setConsensus, t }: { consensus: Record<string, unknown>; setConsensus: (p: Record<string, unknown>) => void; t: ReturnType<typeof useTranslations> }) {
  const refs = (consensus.reference_model_selections as Array<{ providerId: string; model: string }>) ?? [];
  return (
    <div>
      <label className="text-xs font-medium text-muted-foreground">{t('agent.consensusRefModels')}</label>
      <p className="text-[10px] text-muted-foreground/70 mt-0.5">{t('agent.consensusRefModelsDesc')}</p>
      <div className="flex flex-wrap gap-1.5 mt-2">
        {refs.map((sel, idx) => (
          <div key={`${sel.providerId}-${sel.model}-${idx}`} className="flex items-center gap-1.5 rounded-lg bg-muted/50 border border-border/40 px-2.5 py-1.5 text-xs group">
            <ProviderIcon providerId={sel.providerId} size={14} />
            <span className="text-foreground/80 max-w-[120px] truncate">{sel.model}</span>
            <button type="button" className="ml-0.5 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
              onClick={() => { const next = [...refs]; next.splice(idx, 1); setConsensus({ reference_model_selections: next }); }}>
              <X size={12} />
            </button>
          </div>
        ))}
        <ModelPickerPopover
          trigger={
            <button type="button" className="flex items-center gap-1 rounded-lg border border-dashed border-border/60 px-2.5 py-1.5 text-xs text-muted-foreground hover:border-primary/40 hover:text-primary transition-colors">
              <span>+</span><span>{t('agent.consensusAddModel')}</span>
            </button>
          }
          onSelect={(providerId, model) => {
            if (!refs.some((r) => r.providerId === providerId && r.model === model)) {
              setConsensus({ reference_model_selections: [...refs, { providerId, model }] });
            }
          }}
        />
      </div>
      {refs.length === 0 && <p className="text-[10px] text-amber-500/80 mt-1.5">{t('agent.consensusNoModels')}</p>}
    </div>
  );
}

export function ConsensusAggModel({ consensus, setConsensus, t }: { consensus: Record<string, unknown>; setConsensus: (p: Record<string, unknown>) => void; t: ReturnType<typeof useTranslations> }) {
  const aggSel = consensus.aggregator_model_selection as { providerId: string; model: string } | null | undefined;
  return (
    <div>
      <label className="text-xs font-medium text-muted-foreground">{t('agent.consensusAggModel')}</label>
      <p className="text-[10px] text-muted-foreground/70 mt-0.5">{t('agent.consensusAggModelDesc')}</p>
      <div className="flex items-center gap-2 mt-2">
        {aggSel?.providerId && aggSel?.model ? (
          <div className="flex items-center gap-1.5 rounded-lg bg-muted/50 border border-border/40 px-2.5 py-1.5 text-xs group">
            <ProviderIcon providerId={aggSel.providerId} size={14} />
            <span className="text-foreground/80 max-w-[140px] truncate">{aggSel.model}</span>
            <button type="button" className="ml-0.5 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
              onClick={() => setConsensus({ aggregator_model_selection: null })}>
              <X size={12} />
            </button>
          </div>
        ) : (
          <span className="text-[10px] text-muted-foreground/60">{t('agent.consensusUsingPrimary')}</span>
        )}
        <ModelPickerPopover
          trigger={
            <button type="button" className="flex items-center gap-1 rounded-lg border border-dashed border-border/60 px-2 py-1 text-[11px] text-muted-foreground hover:border-primary/40 hover:text-primary transition-colors">
              <span>+</span>
            </button>
          }
          currentSelection={aggSel ?? undefined}
          onSelect={(providerId, model) => setConsensus({ aggregator_model_selection: { providerId, model } })}
        />
      </div>
    </div>
  );
}
