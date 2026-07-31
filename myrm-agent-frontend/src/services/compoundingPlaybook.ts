import { apiRequest } from '@/lib/api';

export type CompoundingChecklistId = 'memory' | 'skills' | 'cron' | 'verify';

export interface CompoundingChecklistItem {
  id: CompoundingChecklistId;
  ready: boolean;
  count: number;
  deep_link: string;
}

export interface CompoundingPlaybookStatus {
  agent_id: string | null;
  items: CompoundingChecklistItem[];
  ready_count: number;
  total_count: number;
}

export async function fetchCompoundingPlaybookStatus(agentId?: string): Promise<CompoundingPlaybookStatus> {
  const query = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : '';
  return apiRequest(`/compounding-playbook/status${query}`);
}
