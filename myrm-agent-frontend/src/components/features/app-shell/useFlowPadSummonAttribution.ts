/**
 * [INPUT]
 * - recordExpertSummonFirstMessageSent (POS: 专家召唤漏斗埋点)
 *
 * [OUTPUT]
 * - SummonAttribution: 一次召唤的归因维度（触发方式/模板类型/是否来自搜索或场景）。
 * - useFlowPadSummonAttribution: begin / clear / reportFirstMessage 三个稳定函数。
 *
 * [POS]
 * FlowPad Inline 的召唤转化归因。记住"当前路由来自哪次专家召唤"，使首条发给该专家的消息
 * 恰好上报一次；路由换走、回退或面板重开时由调用方 clear。
 */
import { useCallback, useRef } from 'react';
import { recordExpertSummonFirstMessageSent } from '@/services/expertSummonMetrics';

export interface SummonAttribution {
  trigger: 'template_card' | 'use_case_chip';
  templateKind: 'team' | 'individual';
  fromSearch: boolean;
  usedUseCase: boolean;
}

interface TrackedSummon {
  attribution: SummonAttribution;
  reported: boolean;
}

export function useFlowPadSummonAttribution() {
  const trackedRef = useRef<TrackedSummon | null>(null);

  const begin = useCallback((attribution: SummonAttribution) => {
    trackedRef.current = { attribution, reported: false };
  }, []);

  const clear = useCallback(() => {
    trackedRef.current = null;
  }, []);

  /** Reports the first message sent to the summoned expert; later messages report nothing. */
  const reportFirstMessage = useCallback(() => {
    const tracked = trackedRef.current;
    if (!tracked || tracked.reported) {
      return;
    }
    tracked.reported = true;
    const { trigger, templateKind, fromSearch, usedUseCase } = tracked.attribution;
    recordExpertSummonFirstMessageSent('flow_pad_inline', trigger, {
      contextKey: 'flowpad:inline',
      templateKind,
      fromSearch,
      usedUseCase,
    });
  }, []);

  return { begin, clear, reportFirstMessage };
}
