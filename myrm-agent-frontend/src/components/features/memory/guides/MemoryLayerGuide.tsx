'use client';

/**
 * [INPUT]
 * next-intl useTranslations (POS: i18n)
 *
 * [OUTPUT]
 * MemoryLayerGuide: Ultra-light four-layer memory guide rendered inside the Memory Types panel.
 *
 * [POS]
 * Lightweight educational strip that groups Myrm memory types into four conceptual layers
 * (working set / task state / long-term memory / raw evidence) so new users understand what
 * each layer holds and where its scope boundary sits. Read-only, no new API, no duplicate
 * counting panels — it only annotates the existing Memory Types grid.
 */

import { useTranslations } from 'next-intl';

interface LayerRow {
  titleKey: string;
  typesKey: string;
  hintKey: string;
}

const LAYERS: LayerRow[] = [
  {
    titleKey: 'commandCenter.layerGuide.workingSet',
    typesKey: 'commandCenter.layerGuide.workingSetTypes',
    hintKey: 'commandCenter.layerGuide.workingSetHint',
  },
  {
    titleKey: 'commandCenter.layerGuide.taskState',
    typesKey: 'commandCenter.layerGuide.taskStateTypes',
    hintKey: 'commandCenter.layerGuide.taskStateHint',
  },
  {
    titleKey: 'commandCenter.layerGuide.longTerm',
    typesKey: 'commandCenter.layerGuide.longTermTypes',
    hintKey: 'commandCenter.layerGuide.longTermHint',
  },
  {
    titleKey: 'commandCenter.layerGuide.rawEvidence',
    typesKey: 'commandCenter.layerGuide.rawEvidenceTypes',
    hintKey: 'commandCenter.layerGuide.rawEvidenceHint',
  },
];

export function MemoryLayerGuide() {
  const t = useTranslations('memory');

  return (
    <div className="mt-3 space-y-2 rounded-lg border border-border/40 bg-background/50 p-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {t('commandCenter.layerGuide.title')}
      </div>
      {LAYERS.map((layer) => (
        <div key={layer.titleKey} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs">
          <span className="font-medium text-foreground">{t(layer.titleKey)}</span>
          <span className="text-primary/80">{t(layer.typesKey)}</span>
          <span className="text-muted-foreground">· {t(layer.hintKey)}</span>
        </div>
      ))}
    </div>
  );
}
