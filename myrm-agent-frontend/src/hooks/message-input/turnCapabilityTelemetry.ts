/**
 * [INPUT]
 * - @/services/turnCapabilityMetrics::recordTurnCapability* (POS: 单轮 Skill/MCP 能力覆写可观测埋点)
 * - @/lib/utils/networkResilience::{FatalNetworkError, isArchiveRestoreActionInvalidError} (POS: 网络错误分类与恢复动作错误识别)
 * - ./turnCapabilityOverrideCore::TurnCapabilitySelection (POS: 单轮能力覆写核心)
 *
 * [OUTPUT]
 * - useTurnCapabilityTelemetry: 每个会话稳定的单轮能力覆写埋点记录器（提交/入队/忙碌回队/终态）。
 * - resolveTerminalTelemetry: 随请求体上报的单轮覆写终态遥测。
 *
 * [POS]
 * 单轮能力覆写在直接发送与排队重放两条链路上的埋点编排，保证 direct 与 queue_drain 口径一致。
 */
import { useMemo } from 'react';
import { FatalNetworkError, isArchiveRestoreActionInvalidError } from '@/lib/utils/networkResilience';
import {
  recordTurnCapabilityBusyRequeued,
  recordTurnCapabilityOverrideApplied,
  recordTurnCapabilityOverrideNoop,
  recordTurnCapabilityQueueEnqueued,
  recordTurnCapabilitySelectionSubmitted,
  recordTurnCapabilitySendFailed,
  type TurnCapabilityFailureReason,
  type TurnCapabilityMetricSource,
} from '@/services/turnCapabilityMetrics';
import type { AgentConfig, TurnCapabilityTerminalTelemetry } from '@/store/chat/types';
import type { TurnCapabilitySelection } from './turnCapabilityOverrideCore';

type SendSource = 'direct' | 'queue_drain';

function getOptionalSelectionCount(values: readonly string[] | null): number | undefined {
  return values === null ? undefined : values.length;
}

function classifyTurnCapabilityFailureReason(error: unknown): TurnCapabilityFailureReason {
  if (isArchiveRestoreActionInvalidError(error)) {
    return 'archive_restore_invalid';
  }
  if (error instanceof Error) {
    if (error.name === 'AbortError') {
      return 'abort';
    }
    if (error instanceof FatalNetworkError && typeof error.status === 'number' && error.status >= 500) {
      return 'server_error';
    }
    const combined = `${error.name} ${error.message}`.toLowerCase();
    if (
      combined.includes('network') ||
      combined.includes('timeout') ||
      combined.includes('fetch') ||
      combined.includes('connection')
    ) {
      return 'network_error';
    }
    if (combined.includes('server') || combined.includes('http') || combined.includes('status')) {
      return 'server_error';
    }
    return 'unknown_error';
  }
  if (error && typeof error === 'object') {
    const maybeMessage = (error as { message?: unknown }).message;
    if (typeof maybeMessage === 'string') {
      const lowerMessage = maybeMessage.toLowerCase();
      if (lowerMessage.includes('network') || lowerMessage.includes('timeout') || lowerMessage.includes('fetch')) {
        return 'network_error';
      }
      if (lowerMessage.includes('server') || lowerMessage.includes('http') || lowerMessage.includes('status')) {
        return 'server_error';
      }
    }
  }
  return 'unknown_error';
}

/** Terminal telemetry travels with the request only when the override actually changed the capability set. */
export function resolveTerminalTelemetry(
  source: SendSource,
  selection: TurnCapabilitySelection | null,
  override: AgentConfig | undefined,
): TurnCapabilityTerminalTelemetry | undefined {
  if (!selection || !override) {
    return undefined;
  }
  return {
    source,
    effectiveSkillCount: override.selectedSkillIds.length,
    effectiveMcpCount: override.selectedMcpNames.length,
  };
}

export function useTurnCapabilityTelemetry(chatId: string | null | undefined) {
  const contextKey = chatId ? `chat:${chatId}` : undefined;

  return useMemo(() => {
    const recordSettled = (
      source: SendSource,
      selection: TurnCapabilitySelection | null,
      override: AgentConfig | undefined,
    ): void => {
      if (!selection) {
        return;
      }
      const selectedSkills = getOptionalSelectionCount(selection.skillIds);
      const selectedMcps = getOptionalSelectionCount(selection.mcpNames);
      if (override) {
        recordTurnCapabilityOverrideApplied(
          source,
          selectedSkills,
          selectedMcps,
          override.selectedSkillIds.length,
          override.selectedMcpNames.length,
          contextKey,
        );
      } else {
        recordTurnCapabilityOverrideNoop(source, selectedSkills, selectedMcps, contextKey);
      }
    };

    return {
      recordSelectionSubmitted: (source: TurnCapabilityMetricSource, selection: TurnCapabilitySelection): void =>
        recordTurnCapabilitySelectionSubmitted(
          source,
          getOptionalSelectionCount(selection.skillIds),
          getOptionalSelectionCount(selection.mcpNames),
          contextKey,
        ),
      recordQueueEnqueued: (source: TurnCapabilityMetricSource, selection: TurnCapabilitySelection): void =>
        recordTurnCapabilityQueueEnqueued(
          source,
          getOptionalSelectionCount(selection.skillIds),
          getOptionalSelectionCount(selection.mcpNames),
          contextKey,
        ),
      recordBusyRequeued: (source: SendSource): void => recordTurnCapabilityBusyRequeued(source, contextKey),
      recordSettled,
      /** A turn that dispatched but ended in an error: the override still counts, and network failures are reported. */
      recordFailed: (
        source: SendSource,
        selection: TurnCapabilitySelection | null,
        override: AgentConfig | undefined,
        error: unknown,
      ): void => {
        recordSettled(source, selection, override);
        if (selection && override) {
          const reason = classifyTurnCapabilityFailureReason(error);
          if (reason === 'network_error') {
            recordTurnCapabilitySendFailed(source, reason, contextKey);
          }
        }
      },
    };
  }, [contextKey]);
}
