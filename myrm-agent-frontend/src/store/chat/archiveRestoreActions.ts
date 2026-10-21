/**
 * [INPUT]
 * - @/store/chat/types::ArchiveRestoreAction, ArchiveRestoreBlockPayload (POS: Chat state and SSE event type definitions)
 *
 * [OUTPUT]
 * - normalizeArchiveRestoreActions: deduplicate and cap typed archive restore actions.
 * - resolveArchiveRestoreActionsForMessage: match pending restore actions against outgoing text.
 * - parseArchiveRestoreBlockPayload: parse archive_restore_blocked status payloads.
 * - parseArchiveRestoreResultPayload: parse successful archive restore result payloads.
 * - buildArchiveRestoreActions: derive typed restore actions from blocked archive payloads.
 *
 * [POS]
 * Typed archive restore action utility layer. Keeps parsing, normalization and send-time
 * matching outside the chat stream reducer and input hook.
 */

import type {
  ArchiveRestoreAction,
  ArchiveRestoreBlockPayload,
  ArchiveRestoreContentFeature,
  ArchiveRestoreRangeHint,
  ArchiveRestoreResultPayload,
} from '@/store/chat/types';

export const MAX_ARCHIVE_RESTORE_ACTIONS_PER_REQUEST = 3;

export function normalizeArchiveRestoreActions(
  actions: ArchiveRestoreAction[],
  limit: number = MAX_ARCHIVE_RESTORE_ACTIONS_PER_REQUEST,
): ArchiveRestoreAction[] {
  const seen = new Set<string>();
  const normalized: ArchiveRestoreAction[] = [];
  for (const action of actions) {
    const restoreArg = action.restoreArg.trim();
    if (!restoreArg || seen.has(restoreArg)) {
      continue;
    }
    seen.add(restoreArg);
    normalized.push({ type: 'archive_restore', restoreArg });
    if (normalized.length >= limit) {
      break;
    }
  }
  return normalized;
}

export function resolveArchiveRestoreActionsForMessage(
  message: string,
  pendingActions: ArchiveRestoreAction[],
): ArchiveRestoreAction[] | undefined {
  const actions = pendingActions.filter((action) => message.includes(action.restoreArg));
  return actions.length > 0 ? actions : undefined;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined;
}

function asStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const strings = value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
  return strings.length > 0 ? strings : undefined;
}

function parseArchiveRestoreRangeHints(value: unknown): ArchiveRestoreRangeHint[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const hints: ArchiveRestoreRangeHint[] = [];
  for (const item of value) {
    const record = asRecord(item);
    const rangeArg = typeof record?.range_arg === 'string' ? record.range_arg.trim() : '';
    if (!rangeArg) {
      continue;
    }
    hints.push({
      range_arg: rangeArg,
      reason: typeof record?.reason === 'string' ? record.reason : undefined,
      start_line: typeof record?.start_line === 'number' ? record.start_line : undefined,
      end_line: typeof record?.end_line === 'number' ? record.end_line : undefined,
      label: typeof record?.label === 'string' ? record.label : undefined,
    });
  }
  return hints.length > 0 ? hints : undefined;
}

function parseArchiveRestoreContentFeatures(value: unknown): ArchiveRestoreContentFeature[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const features: ArchiveRestoreContentFeature[] = [];
  for (const item of value) {
    const record = asRecord(item);
    const featureType = typeof record?.feature_type === 'string' ? record.feature_type : '';
    const count = typeof record?.count === 'number' ? record.count : 0;
    const values = asStringArray(record?.values) ?? [];
    if (!featureType || count <= 0) {
      continue;
    }
    features.push({ feature_type: featureType, count, values });
  }
  return features.length > 0 ? features : undefined;
}

export function parseArchiveRestoreBlockPayload(value: unknown): ArchiveRestoreBlockPayload | undefined {
  const record = asRecord(value);
  if (!record) {
    return undefined;
  }
  const severity = record.severity;
  const parsed: ArchiveRestoreBlockPayload = {
    type: record.type === 'archive_restore_blocked' ? 'archive_restore_blocked' : undefined,
    reason: typeof record.reason === 'string' ? record.reason : undefined,
    message: typeof record.message === 'string' ? record.message : undefined,
    suggested_action: typeof record.suggested_action === 'string' ? record.suggested_action : undefined,
    archive_path: typeof record.archive_path === 'string' ? record.archive_path : undefined,
    estimated_tokens: typeof record.estimated_tokens === 'number' ? record.estimated_tokens : undefined,
    reason_label_key: typeof record.reason_label_key === 'string' ? record.reason_label_key : undefined,
    severity: severity === 'info' || severity === 'warning' || severity === 'critical' ? severity : undefined,
    primary_restore_arg: typeof record.primary_restore_arg === 'string' ? record.primary_restore_arg : undefined,
    recommended_ranges: asStringArray(record.recommended_ranges),
    restore_range_hints: parseArchiveRestoreRangeHints(record.restore_range_hints),
    content_features: parseArchiveRestoreContentFeatures(record.content_features),
    guidance_source: typeof record.guidance_source === 'string' ? record.guidance_source : undefined,
    fallback_reason: typeof record.fallback_reason === 'string' ? record.fallback_reason : undefined,
  };
  if (
    !parsed.message &&
    !parsed.primary_restore_arg &&
    !parsed.recommended_ranges?.length &&
    !parsed.restore_range_hints?.length
  ) {
    return undefined;
  }
  return parsed;
}

function nonNegativeNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : 0;
}

function positiveNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 1 ? value : 0;
}

export function parseArchiveRestoreResultPayload(value: unknown): ArchiveRestoreResultPayload | undefined {
  const record = asRecord(value);
  if (!record) {
    return undefined;
  }
  const archivePath = typeof record.archive_path === 'string' ? record.archive_path.trim() : '';
  const restoreArg = typeof record.restore_arg === 'string' ? record.restore_arg.trim() : '';
  const startLine = positiveNumber(record.start_line);
  const endLine = positiveNumber(record.end_line);
  if (!archivePath || !restoreArg || startLine === 0 || endLine === 0 || startLine > endLine) {
    return undefined;
  }
  return {
    type: record.type === 'archive_restore_result' ? 'archive_restore_result' : undefined,
    outcome: record.outcome === 'restored' ? 'restored' : undefined,
    archive_path: archivePath,
    restore_arg: restoreArg,
    start_line: startLine,
    end_line: endLine,
    restored_line_count: nonNegativeNumber(record.restored_line_count),
    estimated_tokens: nonNegativeNumber(record.estimated_tokens),
    restored_bytes: nonNegativeNumber(record.restored_bytes),
  };
}

export function buildArchiveRestoreActions(payload: ArchiveRestoreBlockPayload | undefined): ArchiveRestoreAction[] {
  if (!payload) {
    return [];
  }
  return normalizeArchiveRestoreActions([
    ...(payload.restore_range_hints?.map((hint) => ({
      type: 'archive_restore' as const,
      restoreArg: hint.range_arg,
    })) ?? []),
    ...(payload.recommended_ranges?.map((restoreArg) => ({ type: 'archive_restore' as const, restoreArg })) ?? []),
    { type: 'archive_restore', restoreArg: payload.primary_restore_arg ?? '' },
  ]);
}
