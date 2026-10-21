/**
 * [INPUT]
 * - services/agent::instantiateTemplate (POS: 模板实例化 API)
 * - services/expertSummonMetrics::* (POS: 漏斗可观测事件上报)
 *
 * [OUTPUT]
 * - instantiateTemplateWithMetrics: 模板召唤统一执行入口（含观测埋点）。
 *
 * [POS]
 * 收敛 TemplateMarket 与 FlowPad 的模板实例化逻辑，确保召唤尝试/成功/失败口径一致。
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
