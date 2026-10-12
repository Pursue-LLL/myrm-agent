/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API client transport)
 *
 * [OUTPUT]
 * Hierarchical Time-Window Activity Compactor DTOs & API clients:
 * - ingestActivityEvent
 * - triggerMicroFold
 * - triggerMacroDistill
 * - synthesizeDailyArchive
 * - getRecentMicroSlices
 * - getRecentMacroFolds
 * - getActivityCompactorTelemetry
 *
 * [POS]
 * Frontend API service for Topic 01 Item 87 (ChatGPT Desktop Skysight-style 10min/6h/24h compaction).
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface IngestActivityEventRequestDTO {
  app_name: string;
  window_title: string;
  action_type?: string;
  event_payload?: string;
  duration_seconds?: number;
}

export interface MicroActivitySliceDTO {
  slice_id: string;
  start_time: string;
  end_time: string;
  primary_app: string;
  raw_event_count: number;
  folded_summary: string;
  unique_windows: string[];
  is_idle: boolean;
  active_minutes: number;
}

export interface MacroMilestoneFoldDTO {
  fold_id: string;
  start_time: string;
  end_time: string;
  milestone_summary: string;
  key_activities: string[];
  micro_slices_count: number;
  tags: string[];
  confidence: number;
}

export interface DailyPreferenceArchiveDTO {
  archive_id: string;
  date_str: string;
  consolidated_facts: string[];
  preference_updates: string[];
  total_raw_events_processed: number;
  macro_folds_count: number;
}

export interface CompactorPipelineTelemetryDTO {
  total_raw_events: number;
  total_micro_slices: number;
  total_macro_folds: number;
  idle_events_dropped: number;
  estimated_tokens_saved: number;
  compression_ratio: number;
}

export interface TriggerMicroFoldRequestDTO {
  force?: boolean;
}

export interface TriggerMacroDistillRequestDTO {
  hours_back?: number;
}

export interface SynthesizeDailyArchiveRequestDTO {
  date_str?: string;
}

export async function ingestActivityEvent(
  req: IngestActivityEventRequestDTO,
): Promise<{ status: string; app_name: string }> {
  return apiRequest<{ status: string; app_name: string }>('/memory/activity-compactor/ingest', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function triggerMicroFold(
  req: TriggerMicroFoldRequestDTO = { force: true },
): Promise<MicroActivitySliceDTO> {
  return apiRequest<MicroActivitySliceDTO>('/memory/activity-compactor/micro-fold', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function triggerMacroDistill(
  req: TriggerMacroDistillRequestDTO = { hours_back: 6 },
): Promise<MacroMilestoneFoldDTO> {
  return apiRequest<MacroMilestoneFoldDTO>('/memory/activity-compactor/macro-distill', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function synthesizeDailyArchive(
  req: SynthesizeDailyArchiveRequestDTO = {},
): Promise<DailyPreferenceArchiveDTO> {
  return apiRequest<DailyPreferenceArchiveDTO>('/memory/activity-compactor/daily-archive', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function getRecentMicroSlices(
  limit = 20,
): Promise<MicroActivitySliceDTO[]> {
  return apiRequest<MicroActivitySliceDTO[]>(
    `/memory/activity-compactor/slices?limit=${encodeURIComponent(limit)}`,
  );
}

export async function getRecentMacroFolds(
  limit = 10,
): Promise<MacroMilestoneFoldDTO[]> {
  return apiRequest<MacroMilestoneFoldDTO[]>(
    `/memory/activity-compactor/folds?limit=${encodeURIComponent(limit)}`,
  );
}

export async function getActivityCompactorTelemetry(): Promise<CompactorPipelineTelemetryDTO> {
  return apiRequest<CompactorPipelineTelemetryDTO>('/memory/activity-compactor/telemetry');
}
