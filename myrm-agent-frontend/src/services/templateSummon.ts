/**
 * [INPUT]
 * - services/agent::instantiateTemplate (POS: 模板实例化 API)
 * - services/expertSummonMetrics::* (POS: 漏斗可观测事件上报)
 *
 * [OUTPUT]
 * - instantiateTemplateWithMetrics: 模板召唤统一执行入口（含观测埋点）。
 * - extractSummonErrorMessage: 提取召唤专家过程中的用户友好错误信息。
 *
 * [POS]
 * 收敛 TemplateMarket 与 FlowPad 的模板实例化逻辑，确保召唤尝试/成功/失败口径一致，透传真实错误。
 */
import { instantiateTemplate, type Agent } from '@/services/agent';
import {
  inferExpertSummonFailureReason,
  recordExpertSummonAttempted,
  recordExpertSummonFailed,
  recordExpertSummonSucceeded,
  type ExpertSummonMetricSurface,
  type ExpertSummonMetricTrigger,
} from '@/services/expertSummonMetrics';
import type { ExpertTemplateKind } from '@/services/templateDiscovery';

/**
 * 提取召唤专家模板时的错误信息。
 * 优先透传底层真实报错（如 ApiError.message、网络连接异常等），
 * 避免通用文案掩盖真正原因。
 */
export function extractSummonErrorMessage(error: unknown, fallbackMessage: string): string {
  if (!error) {
    return fallbackMessage;
  }
  const rawMessage = error instanceof Error ? error.message : typeof error === 'string' ? error : '';
  const trimmed = rawMessage.trim();
  if (!trimmed || trimmed === '[object Object]') {
    return fallbackMessage;
  }
  return trimmed;
}

interface InstantiateTemplateWithMetricsOptions {
  templateId: string;
  surface: ExpertSummonMetricSurface;
  trigger: ExpertSummonMetricTrigger;
  templateKind: ExpertTemplateKind;
  fromSearch: boolean;
  usedUseCase: boolean;
  contextKey?: string;
}

export async function instantiateTemplateWithMetrics(options: InstantiateTemplateWithMetricsOptions): Promise<Agent> {
  recordExpertSummonAttempted(options.surface, options.trigger, {
    contextKey: options.contextKey,
    templateKind: options.templateKind,
    fromSearch: options.fromSearch,
    usedUseCase: options.usedUseCase,
  });
  try {
    const newAgent = await instantiateTemplate(options.templateId);
    recordExpertSummonSucceeded(options.surface, options.trigger, {
      contextKey: options.contextKey,
      templateKind: options.templateKind,
      fromSearch: options.fromSearch,
      usedUseCase: options.usedUseCase,
    });
    return newAgent;
  } catch (error) {
    recordExpertSummonFailed(options.surface, options.trigger, inferExpertSummonFailureReason(error), {
      contextKey: options.contextKey,
      templateKind: options.templateKind,
      fromSearch: options.fromSearch,
      usedUseCase: options.usedUseCase,
    });
    throw error;
  }
}
