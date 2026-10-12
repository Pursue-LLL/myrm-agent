/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API client transport)
 *
 * [OUTPUT]
 * Screen observation memory safety gate & anti-injection DTOs & API clients:
 * - processScreenObservation
 * - getScreenObservationAuditRecords
 *
 * [POS]
 * Frontend API service for ChatGPT Desktop Skysight-style screen observation safety (Topic 01 Item 85).
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export type ObservationSourceType =
  | 'ax_tree'
  | 'ocr_text'
  | 'screenshot_summary'
  | 'browser_dom'
  | 'terminal_output';

export type PromotionStatus =
  | 'transient_observation'
  | 'candidate_pattern'
  | 'promoted_preference'
  | 'rejected_injection';

export interface IngestScreenObservationRequestDTO {
  source_type: ObservationSourceType;
  raw_text: string;
  extracted_statement: string;
  app_name?: string;
  window_title?: string;
  session_id?: string;
  app_bundle_id?: string;
}

export interface ScreenObservationSafetyResponseDTO {
  audit_id: string;
  is_safe: boolean;
  risk_score: number;
  detected_injection_patterns: string[];
  promotion_status: PromotionStatus;
  is_promoted: boolean;
  final_statement: string;
  imperative_detected: boolean;
  explanation: string;
  isolated_prompt_preview: string;
}

export interface ScreenSafetyAuditItemDTO {
  record_id: string;
  session_id: string;
  app_name: string;
  fact_statement: string;
  promotion_status: PromotionStatus;
  risk_score: number;
  imperative_detected: boolean;
  created_at: string;
}

export interface ScreenSafetyAuditListResponseDTO {
  records: ScreenSafetyAuditItemDTO[];
  total_count: number;
}

/**
 * Process raw screen observation evidence through anti-injection fence and descriptive syntax gate.
 */
export async function processScreenObservation(
  payload: IngestScreenObservationRequestDTO,
): Promise<ScreenObservationSafetyResponseDTO> {
  return apiRequest<ScreenObservationSafetyResponseDTO>('/memory/screen-observation/process', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Retrieve recent screen observation safety and gatekeeper audit ledger records.
 */
export async function getScreenObservationAuditRecords(
  limit = 50,
): Promise<ScreenSafetyAuditListResponseDTO> {
  return apiRequest<ScreenSafetyAuditListResponseDTO>(
    `/memory/screen-observation/audit-records?limit=${limit}`,
    {
      method: 'GET',
    },
  );
}
