'use client';

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import { IconDatabase } from '@/components/features/icons/PremiumIcons';
import MemoryMigrationNotice from '@/components/features/memory/settings/MemoryMigrationNotice';
import { Skeleton } from '@/components/primitives/skeleton';
import { EMBEDDING_PROVIDERS, RERANKER_PROVIDERS, getPresetModel } from '@/lib/search/retrievalProviders';
import useRetrievalStore from '@/store/useRetrievalStore';
import { ModelCardTitle } from '../default-model/ModelCardParts';
import SettingsSection from '../sections/SettingsSection';
import AdvancedSetup from './AdvancedSetup';
import { EmbeddingRow, RerankRow } from './CapabilityRows';
import DisclosureNotice from './DisclosureNotice';
import QuickSetup from './QuickSetup';
import {
  disableReranking,
  enableEmbedding,
  enableReranking,
  readQuickCredentials,
  type QuickCredentials,
} from './retrievalSetup';

/**
 * Semantic search (embedding) and reranking behind one provider and key.
 * The quick setup shows while either model is missing; once both are applied, changes go through the advanced section.
 */
const RetrievalCard = memo(() => {
  const t = useTranslations('settings.retrieval');
  const retrieval = useRetrievalStore(
    useShallow((state) => ({
      isInitialized: state.isInitialized,
      embeddingConfig: state.embeddingConfig,
      embeddingApplied: state.embeddingApplied,
      embeddingApplyStatus: state.embeddingApplyStatus,
      embeddingApplyMessage: state.embeddingApplyMessage,
      rerankerConfig: state.rerankerConfig,
      rerankerApplied: state.rerankerApplied,
      rerankerApplyStatus: state.rerankerApplyStatus,
      rerankerApplyMessage: state.rerankerApplyMessage,
      enableAdvancedRetrieval: state.enableAdvancedRetrieval,
    })),
  );
  // Fields the user has changed; the others keep following the store, so a late sync still shows through.
  const [edits, setEdits] = useState<Partial<QuickCredentials>>({});
  const credentials: QuickCredentials = { ...readQuickCredentials(retrieval), ...edits };

  const needsQuickSetup = !retrieval.embeddingApplied || !retrieval.rerankerApplied;

  const handleRerankChange = (checked: boolean) => {
    if (checked) {
      void enableReranking(credentials);
    } else {
      disableReranking();
    }
  };

  return (
    <SettingsSection
      title={
        <ModelCardTitle
          icon={<IconDatabase className="w-5 h-5 text-blue-500" />}
          tint="bg-blue-500/10"
          title={t('card.title')}
        />
      }
      description={t('card.description')}
    >
      {retrieval.isInitialized ? (
        <>
          {needsQuickSetup && (
            <QuickSetup
              credentials={credentials}
              onChange={(edit) => setEdits((current) => ({ ...current, ...edit }))}
            />
          )}
          <EmbeddingRow
            applied={retrieval.embeddingApplied}
            status={retrieval.embeddingApplyStatus}
            message={retrieval.embeddingApplyMessage}
            presetModel={getPresetModel(EMBEDDING_PROVIDERS, credentials.providerId)}
            onEnable={() => void enableEmbedding(credentials)}
          />
          <MemoryMigrationNotice />
          <RerankRow
            applied={retrieval.rerankerApplied}
            checked={retrieval.enableAdvancedRetrieval && retrieval.rerankerApplied}
            status={retrieval.rerankerApplyStatus}
            message={retrieval.rerankerApplyMessage}
            presetModel={getPresetModel(RERANKER_PROVIDERS, credentials.providerId)}
            onChange={handleRerankChange}
          />
          <DisclosureNotice />
          <AdvancedSetup />
        </>
      ) : (
        <div className="space-y-4">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
      )}
    </SettingsSection>
  );
});

RetrievalCard.displayName = 'RetrievalCard';

export default RetrievalCard;
