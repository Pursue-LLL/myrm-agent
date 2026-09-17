/**
 * Tool Guidance and Experience Evolution API Client.
 *
 * Provides methods to inspect distilled golden rules per tool,
 * toggle pinned status, and delete obsolete guidance.
 */

import { apiRequest } from '@/lib/api';

export interface ToolGuidanceItemDTO {
  id: string;
  tool_name: string;
  rule_text: string;
  trigger_pattern: string;
  confidence: number;
  is_pinned: boolean;
  env_fingerprint: string | null;
  agent_id: string | null;
  source: string;
  hit_count: number;
  created_at: string;
  updated_at: string;
}

export interface ToolGuidanceGroupDTO {
  tool_name: string;
  guidelines: string[];
  has_pinned: boolean;
  items: ToolGuidanceItemDTO[];
}

export interface ToolGuidanceListResponse {
  tools: ToolGuidanceGroupDTO[];
  total_tools: number;
  total_rules: number;
}

export interface PinGuidanceResponse {
  rule_id: string;
  is_pinned: boolean;
  status: string;
}

export async function getToolGuidance(): Promise<ToolGuidanceListResponse> {
  return apiRequest<ToolGuidanceListResponse>('/api/v1/memory/tool-guidance');
}

export async function pinToolGuidance(ruleId: string, isPinned: boolean): Promise<PinGuidanceResponse> {
  return apiRequest<PinGuidanceResponse>('/api/v1/memory/tool-guidance/pin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rule_id: ruleId, is_pinned: isPinned }),
  });
}

export async function deleteToolGuidance(ruleId: string): Promise<{ status: string; rule_id: string }> {
  return apiRequest<{ status: string; rule_id: string }>(`/api/v1/memory/tool-guidance/${ruleId}`, {
    method: 'DELETE',
  });
}
