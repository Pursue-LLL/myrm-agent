import { apiRequest } from '@/lib/api';
import type { Agent } from './agent';

export interface TeamMemberBrief {
  role: string;
  name: string;
  description?: string;
}

export interface TemplateSettingsPreview {
  enabled_builtin_tools: string[];
  skill_ids: string[];
  prebuilt_skill_ids: string[];
  mcp_ids: string[];
  memory_preset: string;
  deploy_mode: string;
  sandbox_bound_note?: string | null;
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
  settings_preview?: TemplateSettingsPreview;
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
