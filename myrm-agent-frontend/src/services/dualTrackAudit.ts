/**
 * [INPUT]
 * - @/lib/api::apiRequest, getApiUrl (POS: unified frontend HTTP client)
 *
 * [OUTPUT]
 * - DualTrackAuditEntryItem, RuleTriggerHitItem, DualTrackAuditStatsResponse
 * - dualTrackAuditService (queries entries, fetches stats, exports compliance dossiers)
 *
 * [POS]
 * REST client for /security/audit/dual-track/* — Dual-Track Prior Audit & Compliance Telemetry.
 */

import { apiRequest, getApiUrl } from '@/lib/api';

export interface DualTrackAuditEntryItem {
  entryId: string;
  sessionId: string;
  agentId: string;
  toolName: string;
  intentSummary: string;
  rawIntentArgs: Record<string, unknown>;
  ruleName: string;
  state: 'INTENT_LOGGED' | 'COMPLETED' | 'REFUSED' | 'FAILED';
  outcome: 'PERMITTED' | 'REFUSED' | 'FAILED';
  isHumanTakeTheWheel: boolean;
  createdAt: string;
  completedAt: string | null;
  latencyMs: number;
  outputLength: number;
  errorMessage: string | null;
}

export interface RuleTriggerHitItem {
  ruleName: string;
  triggerCount: number;
  refusedCount: number;
  permittedCount: number;
  failedCount: number;
  refusalRate: number;
  sampleTargets: string[];
}

export interface DualTrackAuditStatsResponse {
  totalEntries: number;
  permittedCount: number;
  refusedCount: number;
  failedCount: number;
  humanTakeTheWheelCount: number;
  complianceRate: number;
  avgLatencyMs: number;
  topRulesTriggered: RuleTriggerHitItem[];
}

export const dualTrackAuditService = {
  async getEntries(params?: {
    sessionId?: string;
    agentId?: string;
    outcome?: string;
    limit?: number;
  }): Promise<DualTrackAuditEntryItem[]> {
    const query = new URLSearchParams();
    if (params?.sessionId) query.set('session_id', params.sessionId);
    if (params?.agentId) query.set('agent_id', params.agentId);
    if (params?.outcome) query.set('outcome', params.outcome);
    if (params?.limit) query.set('limit', String(params.limit));

    const qs = query.toString();
    const endpoint = `/security/audit/dual-track/entries${qs ? `?${qs}` : ''}`;
    return apiRequest<DualTrackAuditEntryItem[]>(endpoint);
  },

  async getStats(params?: {
    sessionId?: string;
    agentId?: string;
  }): Promise<DualTrackAuditStatsResponse> {
    const query = new URLSearchParams();
    if (params?.sessionId) query.set('session_id', params.sessionId);
    if (params?.agentId) query.set('agent_id', params.agentId);

    const qs = query.toString();
    const endpoint = `/security/audit/dual-track/stats${qs ? `?${qs}` : ''}`;
    return apiRequest<DualTrackAuditStatsResponse>(endpoint);
  },

  getExportUrl(params?: {
    format?: 'json' | 'csv' | 'markdown';
    sessionId?: string;
    agentId?: string;
  }): string {
    const query = new URLSearchParams();
    query.set('format', params?.format ?? 'json');
    if (params?.sessionId) query.set('session_id', params.sessionId);
    if (params?.agentId) query.set('agent_id', params.agentId);

    return getApiUrl(`/security/audit/dual-track/export?${query.toString()}`);
  },
};
