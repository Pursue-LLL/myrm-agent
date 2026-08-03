'use client';

import { X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import ProviderIcon from '@/components/features/settings/model-service/ProviderIcon';
import ModelPickerPopover from '@/components/features/app-shell/model-picker-popover';

/** Reference model picker shared by MoA overlay settings. */
export function ConsensusRefModels({
  consensus,
  setConsensus,
  t,
  noModelsKey = 'consensusNoModels',
}: {
  consensus: Record<string, unknown>;
  setConsensus: (p: Record<string, unknown>) => void;
  t: ReturnType<typeof useTranslations>;
  noModelsKey?: string;
}) {
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
      {refs.length === 0 && <p className="text-[10px] text-amber-500/80 mt-1.5">{t(`agent.${noModelsKey}`)}</p>}
    </div>
  );
}
