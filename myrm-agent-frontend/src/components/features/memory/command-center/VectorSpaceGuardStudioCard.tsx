/**
 * [INPUT]
 * @/services/memory/vectorSpaceGuard::(fetchVectorSpaceStatus, validateVectorSpace, bindVectorSpace, reindexVectorSpace, SpaceFingerprintDTO, SpaceStatusResponse, SpaceValidateResponse, SpaceReindexResponse)
 * ./VectorSpaceGuardHudBar::VectorSpaceGuardHudBar
 * ./VectorSpaceConsistencyCheckerCard::VectorSpaceConsistencyCheckerCard
 * ./VectorSpaceReindexerCard::VectorSpaceReindexerCard
 * ./vectorSpaceGuardFallbacks::(FALLBACK_SPACE_STATUS, FALLBACK_VALIDATE_RESPONSE, FALLBACK_REINDEX_RESPONSE)
 * lucide-react::ShieldCheck, AlertCircle
 *
 * [OUTPUT]
 * Component: VectorSpaceGuardStudioCard
 *
 * [POS]
 * Studio card orchestrating Item 131 EmbeddingModelDimensionAndVectorSpaceGuardSuite.
 * Strictly typed with zero `any`. Full a11y compliance. Single file < 300 lines.
 */

'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { ShieldCheck, AlertCircle } from 'lucide-react';
import {
  fetchVectorSpaceStatus,
  validateVectorSpace,
  bindVectorSpace,
  reindexVectorSpace,
  type SpaceFingerprintDTO,
  type SpaceStatusResponse,
  type SpaceValidateResponse,
  type SpaceReindexResponse,
} from '@/services/memory';
import { VectorSpaceGuardHudBar } from './VectorSpaceGuardHudBar';
import { VectorSpaceConsistencyCheckerCard } from './VectorSpaceConsistencyCheckerCard';
import { VectorSpaceReindexerCard } from './VectorSpaceReindexerCard';
import {
  FALLBACK_SPACE_STATUS,
  FALLBACK_VALIDATE_RESPONSE,
  FALLBACK_REINDEX_RESPONSE,
} from './vectorSpaceGuardFallbacks';

interface VectorSpaceGuardStudioCardProps {
  initialCollection?: string;
}

export const VectorSpaceGuardStudioCard: React.FC<
  VectorSpaceGuardStudioCardProps
> = ({ initialCollection = 'working_memory' }) => {
  const [collection, setCollection] = useState<string>(initialCollection);
  const [status, setStatus] = useState<SpaceStatusResponse | null>(null);
  const [validateResult, setValidateResult] =
    useState<SpaceValidateResponse | null>(null);
  const [reindexResult, setReindexResult] =
    useState<SpaceReindexResponse | null>(null);

  const [isLoadingStatus, setIsLoadingStatus] = useState<boolean>(false);
  const [isValidating, setIsValidating] = useState<boolean>(false);
  const [isBinding, setIsBinding] = useState<boolean>(false);
  const [isReindexing, setIsReindexing] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadSpaceStatus = useCallback(async (targetCollection: string) => {
    if (!targetCollection.trim()) return;
    setIsLoadingStatus(true);
    setErrorMessage(null);
    try {
      const res = await fetchVectorSpaceStatus(targetCollection);
      setStatus(res);
    } catch {
      setStatus({ ...FALLBACK_SPACE_STATUS, collection: targetCollection });
      setErrorMessage('无法连接向量空间守卫服务，已载入离线降级状态');
    } finally {
      setIsLoadingStatus(false);
    }
  }, []);

  useEffect(() => {
    void loadSpaceStatus(collection);
  }, [collection, loadSpaceStatus]);

  const handleValidate = async (
    targetCol: string,
    fp: SpaceFingerprintDTO,
    autoBind: boolean
  ) => {
    setIsValidating(true);
    setErrorMessage(null);
    try {
      const res = await validateVectorSpace({
        collection: targetCol,
        fingerprint: fp,
        auto_bind_if_empty: autoBind,
      });
      setValidateResult(res);
      if (autoBind && res.is_valid) {
        void loadSpaceStatus(targetCol);
      }
    } catch {
      setValidateResult({
        ...FALLBACK_VALIDATE_RESPONSE,
        current_fingerprint: fp,
      });
      setErrorMessage('执行空间校验失败，已返回默认模拟校验结果');
    } finally {
      setIsValidating(false);
    }
  };

  const handleBind = async (targetCol: string, fp: SpaceFingerprintDTO) => {
    setIsBinding(true);
    setErrorMessage(null);
    try {
      await bindVectorSpace({
        collection: targetCol,
        fingerprint: fp,
        total_vectors_indexed: status?.total_vectors_indexed ?? 0,
      });
      await loadSpaceStatus(targetCol);
    } catch {
      setErrorMessage('绑定空间指纹失败');
    } finally {
      setIsBinding(false);
    }
  };

  const handleReindex = async (
    targetCol: string,
    targetFp: SpaceFingerprintDTO,
    sampleItems: string[]
  ) => {
    setIsReindexing(true);
    setErrorMessage(null);
    try {
      const res = await reindexVectorSpace({
        collection: targetCol,
        target_fingerprint: targetFp,
        sample_items: sampleItems,
      });
      setReindexResult(res);
      await loadSpaceStatus(targetCol);
    } catch {
      setReindexResult({
        ...FALLBACK_REINDEX_RESPONSE,
        collection: targetCol,
      });
      setErrorMessage('执行空间迁移重索引失败，已载入离线模拟结果');
    } finally {
      setIsReindexing(false);
    }
  };

  return (
    <section
      aria-labelledby="vector-space-guard-heading"
      className="p-6 rounded-2xl bg-card/60 backdrop-blur border border-border space-y-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-primary/10 text-primary">
            <ShieldCheck className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <h2
              id="vector-space-guard-heading"
              className="text-lg font-semibold text-foreground tracking-tight"
            >
              向量空间与模型维度守卫
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              严格守卫 Embedding 模型维度与基底一致性，杜绝多模型混用基底污染
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <label
            htmlFor="target-collection-input"
            className="text-xs text-muted-foreground font-medium"
          >
            当前集合：
          </label>
          <input
            id="target-collection-input"
            type="text"
            value={collection}
            onChange={(e) => setCollection(e.target.value)}
            className="px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
      </div>

      {errorMessage && (
        <div
          role="alert"
          className="flex items-center gap-2 p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-xs"
        >
          <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
          <span>{errorMessage}</span>
        </div>
      )}

      <VectorSpaceGuardHudBar
        status={status}
        isLoading={isLoadingStatus}
        onRefresh={() => void loadSpaceStatus(collection)}
      />

      <div className="grid grid-cols-1 gap-6">
        <VectorSpaceConsistencyCheckerCard
          collection={collection}
          onValidate={handleValidate}
          onBind={handleBind}
          validateResult={validateResult}
          isValidating={isValidating}
          isBinding={isBinding}
        />

        <VectorSpaceReindexerCard
          collection={collection}
          onReindex={handleReindex}
          reindexResult={reindexResult}
          isReindexing={isReindexing}
        />
      </div>
    </section>
  );
};
