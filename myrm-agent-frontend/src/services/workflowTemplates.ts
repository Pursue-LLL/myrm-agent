import { apiRequest } from '@/lib/api';

export interface WorkflowTemplateSummary {
  template_id: string;
  display_name: string;
  script_hash: string;
  trust_latch: boolean;
  required_agent_types: string[];
  placeholders: string[];
  created_at: string;
  updated_at: string;
}

export interface WorkflowTemplateDetailResponse {
  template: WorkflowTemplateSummary;
  script_code: string;
  bound_cron_count: number;
}

export interface WorkflowTemplateListResponse {
  templates: WorkflowTemplateSummary[];
}

export interface SaveWorkflowTemplateFromRunPayload {
  chat_id: string;
  message_id: string;
  template_id: string;
  display_name: string;
  trust_latch?: boolean;
}

export interface UpsertWorkflowTemplatePayload {
  display_name: string;
  script_code: string;
  trust_latch?: boolean;
}

export async function fetchWorkflowTemplates(): Promise<WorkflowTemplateListResponse> {
  return apiRequest('/workflow-templates');
}

export async function fetchWorkflowTemplateDetail(
  templateId: string,
): Promise<WorkflowTemplateDetailResponse> {
  return apiRequest(`/workflow-templates/${encodeURIComponent(templateId)}`);
}

export async function saveWorkflowTemplateFromRun(
  payload: SaveWorkflowTemplateFromRunPayload,
): Promise<WorkflowTemplateSummary> {
  return apiRequest('/workflow-templates/from-run', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function upsertWorkflowTemplate(
  templateId: string,
  payload: UpsertWorkflowTemplatePayload,
): Promise<WorkflowTemplateSummary> {
  return apiRequest(`/workflow-templates/${encodeURIComponent(templateId)}`, {
    method: 'PUT',
    body: JSON.stringify({
      displayName: payload.display_name,
      scriptCode: payload.script_code,
      trustLatch: payload.trust_latch ?? false,
    }),
  });
}

export async function deleteWorkflowTemplate(templateId: string): Promise<{ deleted: boolean }> {
  return apiRequest(`/workflow-templates/${encodeURIComponent(templateId)}`, {
    method: 'DELETE',
  });
}
