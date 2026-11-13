import { apiRequest } from '@/lib/api';
import type { Agent } from './agent';

export interface TeamMemberBrief {
  role: string;
  name: string;
  description?: string;
}

export interface TemplateListItem {
  id: string;
  name: string;
  description?: string;
  avatar_url?: string;
  agent_type: string;
  category?: string;
  is_pareto_preset?: boolean;
  cost_reduction_ratio?: number;
  members?: TeamMemberBrief[];
  use_cases?: string[];
}

export async function getTemplates(): Promise<TemplateListItem[]> {
  return apiRequest<TemplateListItem[]>('/agents/templates', { method: 'GET', silent: true });
}

export async function instantiateTemplate(templateId: string): Promise<Agent> {
  return apiRequest<Agent>(`/agents/instantiate-template/${templateId}`, {
    method: 'POST',
    silent: true,
  });
}
