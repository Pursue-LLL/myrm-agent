/**
 * Bitemporal Truth Maintenance and Justification Reasoning API Client.
 * Connects frontend inspection dashboard to dual-timeline coordinates,
 * non-destructive retraction, and justification cascade evaluation.
 */

import { apiClient } from '@/services/api';

export interface TimeIntervalDTO {
  start: number;
  end: number | null;
}

export interface BitemporalCoordinatesDTO {
  valid_interval: TimeIntervalDTO;
  known_interval: TimeIntervalDTO;
}

export interface EvidenceRecordDTO {
  evidence_id: string;
  content: string;
  evidence_type: string;
  bitemporal: BitemporalCoordinatesDTO;
  confidence: number;
  metadata: Record<string, string>;
}

export interface RecordFactRequest {
  evidence_id: string;
  content: string;
  valid_start: number;
  valid_end?: number | null;
  known_start?: number | null;
  confidence?: number;
  metadata?: Record<string, string>;
}

export interface DeriveInferenceRequest {
  inference_id: string;
  content: string;
  premise_ids: string[];
  justification: string;
  valid_start?: number | null;
  valid_end?: number | null;
  known_start?: number | null;
  causal_distance?: number;
  confidence?: number;
  metadata?: Record<string, string>;
}

export interface RetractRecordRequest {
  evidence_id: string;
  retracted_at?: number | null;
}

export interface RetractRecordResponse {
  success: boolean;
  evidence_id: string;
  retracted_at: number;
}

export interface TemporalQueryRequest {
  as_of_valid_time?: number | null;
  as_of_known_time?: number | null;
  require_active_support?: boolean;
  min_confidence?: number;
  evidence_types?: string[] | null;
}

export interface TemporalQueryResponse {
  total: number;
  records: EvidenceRecordDTO[];
  as_of_valid_time: number;
  as_of_known_time: number;
}

export interface SnapshotRequest {
  as_of_valid_time?: number | null;
  as_of_known_time?: number | null;
}

export interface SnapshotResponse {
  active_evidences: EvidenceRecordDTO[];
  retracted_evidences: EvidenceRecordDTO[];
  active_inferences: EvidenceRecordDTO[];
  invalidated_inferences: EvidenceRecordDTO[];
  as_of_valid_time: number;
  as_of_known_time: number;
  total_count: number;
}

export interface BitemporalTmsHealthResponse {
  status: string;
  module: string;
  version: string;
}

export const bitemporalTmsApi = {
  /** Record external ground truth fact with bitemporal intervals */
  async recordFact(request: RecordFactRequest): Promise<EvidenceRecordDTO> {
    return apiClient.post<EvidenceRecordDTO>(
      '/memory/bitemporal-tms/facts',
      request
    );
  },

  /** Derive reasoned inference with justification links to premises */
  async deriveInference(request: DeriveInferenceRequest): Promise<EvidenceRecordDTO> {
    return apiClient.post<EvidenceRecordDTO>(
      '/memory/bitemporal-tms/inferences',
      request
    );
  },

  /** Non-destructively retract an evidence record, invalidating active support */
  async retractRecord(request: RetractRecordRequest): Promise<RetractRecordResponse> {
    return apiClient.post<RetractRecordResponse>(
      '/memory/bitemporal-tms/retract',
      request
    );
  },

  /** Query active records at target bitemporal coordinates */
  async queryActive(request: TemporalQueryRequest): Promise<TemporalQueryResponse> {
    return apiClient.post<TemporalQueryResponse>(
      '/memory/bitemporal-tms/query',
      request
    );
  },

  /** Project partitioned snapshot of active vs invalidated entities */
  async projectSnapshot(request: SnapshotRequest): Promise<SnapshotResponse> {
    return apiClient.post<SnapshotResponse>(
      '/memory/bitemporal-tms/snapshot',
      request
    );
  },

  /** Retrieve health status of bitemporal TMS subsystem */
  async getHealth(): Promise<BitemporalTmsHealthResponse> {
    return apiClient.get<BitemporalTmsHealthResponse>(
      '/memory/bitemporal-tms/health'
    );
  },
};
