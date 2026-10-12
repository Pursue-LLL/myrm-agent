/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Knowledge Graph Pre-Extraction Screening & Anti-Poisoning DTOs and API clients:
 * - screenKGContent
 * - getKGScreeningAuditLog
 *
 * [POS]
 * Frontend API client for evaluating text candidates against prompt injection and memory poisoning before graph extraction.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface ThreatFindingDTO {
  category: string;
  matched_pattern: string;
  snippet: string;
  position: number;
  risk_level: string;
  description: string;
}

export interface ScreenContentRequestDTO {
  text: string;
  source_uri?: string;
  sanitize_if_possible?: boolean;
}

export interface ScreenContentResponseDTO {
  verdict: 'clean' | 'sanitized' | 'poison_blocked' | string;
  is_blocked: boolean;
  findings: ThreatFindingDTO[];
  original_length: number;
  sanitized_content: string;
  risk_score: number;
}

export interface ScreeningAuditRecordDTO {
  audit_id: string;
  timestamp: number;
  source_uri: string;
  verdict: string;
  risk_score: number;
  findings_count: number;
  findings_summary: string[];
  sanitized_applied: boolean;
}

export interface ScreeningAuditListResponseDTO {
  records: ScreeningAuditRecordDTO[];
  total_count: number;
}

/**
 * Screen raw text candidate against prompt injection, hidden HTML comments, and memory poisoning.
 */
export async function screenKGContent(
  req: ScreenContentRequestDTO
): Promise<ScreenContentResponseDTO> {
  return apiRequest<ScreenContentResponseDTO>('/memory/kg/screen-content', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

/**
 * Retrieve recent security screening audit entries.
 */
export async function getKGScreeningAuditLog(
  limit: number = 50
): Promise<ScreeningAuditListResponseDTO> {
  return apiRequest<ScreeningAuditListResponseDTO>(
    `/memory/kg/screening-audit-log?limit=${limit}`,
    {
      method: 'GET',
    }
  );
}
