/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: unified API request function)
 *
 * [OUTPUT]
 * - Commitment types and API functions for the commitment tracking system.
 *
 * [POS]
 * Frontend service layer for commitment tracking. Provides typed API
 * functions for listing, dismissing, and snoozing commitments.
 */

import { apiRequest } from '@/lib/api';

export interface Commitment {
  id: string;
  agent_id: string;
  user_id: string;
  channel: string;
  kind: 'event_check_in' | 'deadline_check' | 'care_check_in' | 'open_loop';
  sensitivity: 'routine' | 'personal' | 'care';
  status: 'pending' | 'sent' | 'dismissed' | 'snoozed' | 'expired';
  reason: string;
  suggested_text: string;
  dedupe_key: string;
  confidence: number;
  due_earliest_ms: number;
  due_latest_ms: number;
  due_timezone: string;
  source_chat_id: string | null;
  attempts: number;
  created_at: string;
  snoozed_until_ms: number | null;
}

export interface CommitmentListResponse {
  items: Commitment[];
  total: number;
}

export async function fetchCommitments(params?: {
  status?: string;
  agent_id?: string;
  limit?: number;
}): Promise<CommitmentListResponse> {
  const query = new URLSearchParams();
  if (params?.status) query.set('status', params.status);
  if (params?.agent_id) query.set('agent_id', params.agent_id);
  if (params?.limit) query.set('limit', String(params.limit));

  const qs = query.toString();
  return apiRequest<CommitmentListResponse>(`/memory/follow-ups${qs ? `?${qs}` : ''}`);
}

export async function dismissCommitment(id: string): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/memory/follow-ups/${id}/dismiss`, {
    method: 'POST',
  });
}

export async function snoozeCommitment(id: string, untilMs: number): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/memory/follow-ups/${id}/snooze`, {
    method: 'POST',
    body: JSON.stringify({ until_ms: untilMs }),
  });
}
