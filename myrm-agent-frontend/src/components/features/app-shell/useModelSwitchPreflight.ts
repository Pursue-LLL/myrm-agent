/**
 * [INPUT] @/services/llm-config::fetchModelSwitchPreflight (POS: 模型切换压缩预检), ./model-picker-catalog (POS: 预检请求构造)
 * [OUTPUT] useModelSwitchPreflight: 弹层打开且有会话 token 估算时，按候选模型批量预检，返回 providerId/model 到预检结果的映射
 * [POS] ModelPickerPopover 的压缩预警数据层；同一请求签名只发一次。
 */

import { useEffect, useRef, useState } from 'react';
import {
  fetchModelSwitchPreflight,
  type ModelCapabilities,
  type ModelSwitchPreflightResult,
} from '@/services/llm-config';
import type { ProviderConfig } from '@/store/config/providerTypes';
import {
  buildPreflightPairs,
  buildPreflightSignature,
  mapPreflightResults,
  type EnabledModel,
} from './model-picker-catalog';

interface UseModelSwitchPreflightParams {
  open: boolean;
  enabledModels: EnabledModel[];
  providers: ProviderConfig[];
  capabilities: Record<string, ModelCapabilities>;
  /** 当前会话估算 tokens；无值或 <= 0 时不预检 */
  estimatedTokens: number | null | undefined;
  compressStartRatio: number | null | undefined;
  promptMode: string | null | undefined;
  turnCount: number | null | undefined;
  chatId: string | null | undefined;
}

export function useModelSwitchPreflight({
  open,
  enabledModels,
  providers,
  capabilities,
  estimatedTokens,
  compressStartRatio,
  promptMode,
  turnCount,
  chatId,
}: UseModelSwitchPreflightParams): Record<string, ModelSwitchPreflightResult> {
  // 压缩预检结果：key = providerId/model
  const [preflightMap, setPreflightMap] = useState<Record<string, ModelSwitchPreflightResult>>({});
  const preflightRequestedRef = useRef<string>('');

  useEffect(() => {
    if (!open || !estimatedTokens || estimatedTokens <= 0 || Object.keys(capabilities).length === 0) {
      return;
    }
    const pairs = buildPreflightPairs(enabledModels, providers, capabilities);
    if (pairs.length === 0) {
      return;
    }

    const signature = buildPreflightSignature(
      { chatId, estimatedTokens, compressStartRatio, promptMode, turnCount },
      pairs,
    );
    if (preflightRequestedRef.current === signature) {
      return;
    }
    preflightRequestedRef.current = signature;

    fetchModelSwitchPreflight(
      estimatedTokens,
      pairs.map((p) => ({ model: p.liteName, max_input_tokens: p.maxInput })),
      compressStartRatio,
      promptMode,
      turnCount,
      chatId,
    ).then((results) => {
      setPreflightMap(mapPreflightResults(pairs, results));
    });
  }, [
    open,
    estimatedTokens,
    capabilities,
    enabledModels,
    providers,
    compressStartRatio,
    promptMode,
    turnCount,
    chatId,
  ]);

  return preflightMap;
}
