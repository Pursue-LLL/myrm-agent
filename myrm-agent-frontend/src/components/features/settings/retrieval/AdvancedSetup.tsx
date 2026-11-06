'use client';

import { memo, useState, type ComponentProps } from 'react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import { IconChevronDown, IconSliders } from '@/components/features/icons/PremiumIcons';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/primitives/collapsible';
import { EMBEDDING_PROVIDERS, RERANKER_PROVIDERS } from '@/lib/search/retrievalProviders';
import useRetrievalStore from '@/store/useRetrievalStore';
import ProviderModelSelector from './ProviderModelSelector';

interface RoleSelectorProps extends ComponentProps<typeof ProviderModelSelector> {
  title: string;
}

function RoleSelector({ title, ...selector }: RoleSelectorProps) {
  return (
    <section className="space-y-3">
      <h3 className="text-sm font-medium text-foreground">{title}</h3>
      <div className="rounded-xl border border-border bg-muted/30 p-5">
        <ProviderModelSelector {...selector} />
      </div>
    </section>
  );
}

/** Per-model configuration: different providers, custom models, or a self-hosted OpenAI-compatible endpoint. */
const AdvancedSetup = memo(() => {
  const t = useTranslations('settings.retrieval');
  const [open, setOpen] = useState(false);
  const retrieval = useRetrievalStore(
    useShallow((state) => ({
      embeddingConfig: state.embeddingConfig,
      embeddingApplied: state.embeddingApplied,
      embeddingApplyStatus: state.embeddingApplyStatus,
      embeddingApplyMessage: state.embeddingApplyMessage,
      setEmbeddingConfig: state.setEmbeddingConfig,
      applyEmbedding: state.applyEmbedding,
      rerankerConfig: state.rerankerConfig,
      rerankerApplied: state.rerankerApplied,
      rerankerApplyStatus: state.rerankerApplyStatus,
      rerankerApplyMessage: state.rerankerApplyMessage,
      setRerankerConfig: state.setRerankerConfig,
      applyReranker: state.applyReranker,
    })),
  );

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex w-full items-center justify-between gap-3 rounded-xl border border-border/50 bg-background/50 px-5 py-3.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          <span className="flex items-center gap-2">
            <IconSliders className="h-4 w-4 text-muted-foreground" />
            {t('advanced.title')}
          </span>
          <IconChevronDown
            className={`h-4 w-4 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`}
          />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-4 space-y-6">
        <div className="space-y-1.5 text-xs leading-relaxed text-muted-foreground">
          <p>{t('hint.options')}</p>
          <p>{t('hint.recommendation')}</p>
          <p>
            {t('hint.deployTip')}
            <span className="ml-2 rounded bg-muted/50 px-2 py-0.5 font-mono">{t('hint.deployQuestion')}</span>
          </p>
        </div>
        <RoleSelector
          title={t('advanced.embeddingModel')}
          value={retrieval.embeddingConfig}
          onChange={retrieval.setEmbeddingConfig}
          providers={EMBEDDING_PROVIDERS}
          applyStatus={retrieval.embeddingApplyStatus}
          applyMessage={retrieval.embeddingApplyMessage}
          isApplied={retrieval.embeddingApplied}
          onApply={retrieval.applyEmbedding}
        />
        <RoleSelector
          title={t('advanced.rerankerModel')}
          value={retrieval.rerankerConfig}
          onChange={retrieval.setRerankerConfig}
          providers={RERANKER_PROVIDERS}
          applyStatus={retrieval.rerankerApplyStatus}
          applyMessage={retrieval.rerankerApplyMessage}
          isApplied={retrieval.rerankerApplied}
          onApply={retrieval.applyReranker}
        />
      </CollapsibleContent>
    </Collapsible>
  );
});

AdvancedSetup.displayName = 'AdvancedSetup';

export default AdvancedSetup;
