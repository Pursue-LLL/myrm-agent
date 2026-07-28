/**
 * 配置验证状态检查 Hook
 * 用于检查所有必需的配置是否已验证并准备就绪
 *
 * 验证策略：
 * - 主模型：所有模式必需
 * - 轻量模型：所有模式必需（用于上下文摘要等轻量任务）
 * - 嵌入模型：仅当高级检索开启时必需（网页抓取向量检索、知识库索引等）
 * - 重排序模型：仅当高级检索开启时必需（网络搜索重排序、网页抓取精排等）
 */

import { useMemo } from 'react';
import useRetrievalStore from '@/store/useRetrievalStore';
import useProviderStore from '@/store/useProviderStore';

export interface ConfigValidationResult {
  isValid: boolean;
  missingConfigs: string[];
  invalidConfigs: string[];
}

/**
 * 检查所有配置是否有效
 *
 * 验证策略：
 * - 主模型和轻量模型始终必需
 * - 嵌入和重排序模型仅在 enableAdvancedRetrieval=true 时检查
 * - 已应用（applied=true）即视为有效
 */
export function useConfigValidation(): ConfigValidationResult {
  const { embeddingConfig, embeddingApplied, rerankerConfig, rerankerApplied, enableAdvancedRetrieval } =
    useRetrievalStore();

  const { defaultModelConfig } = useProviderStore();

  return useMemo(() => {
    const missingConfigs: string[] = [];
    const invalidConfigs: string[] = [];

    // 检查主模型（baseModel）
    const baseModelSelection = defaultModelConfig?.baseModel?.primary;
    if (!baseModelSelection || !baseModelSelection.providerId || !baseModelSelection.model) {
      missingConfigs.push('chatModel');
    }

    // 检查轻量模型（liteModel）- 用于上下文摘要等轻量任务
    const liteModelSelection = defaultModelConfig?.liteModel?.primary;
    if (!liteModelSelection || !liteModelSelection.providerId || !liteModelSelection.model) {
      missingConfigs.push('reasoningModel');
    }

    // 仅当高级检索开启时，才检查嵌入和重排序模型
    if (enableAdvancedRetrieval) {
      if (!embeddingConfig.provider || !embeddingConfig.model || !embeddingConfig.apiKey) {
        missingConfigs.push('embedding');
      } else if (!embeddingApplied) {
        invalidConfigs.push('embedding');
      }

      if (!rerankerConfig.provider || !rerankerConfig.model || !rerankerConfig.apiKey) {
        missingConfigs.push('reranker');
      } else if (!rerankerApplied) {
        invalidConfigs.push('reranker');
      }
    }

    const isValid = missingConfigs.length === 0 && invalidConfigs.length === 0;

    return {
      isValid,
      missingConfigs,
      invalidConfigs,
    };
  }, [defaultModelConfig, embeddingConfig, embeddingApplied, rerankerConfig, rerankerApplied, enableAdvancedRetrieval]);
}
