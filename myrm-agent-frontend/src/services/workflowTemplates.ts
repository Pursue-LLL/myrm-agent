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

interface ApiWorkflowTemplateSummary {
  templateId?: string;
  displayName?: string;
  scriptHash?: string;
  trustLatch?: boolean;
  requiredAgentTypes?: string[];
  placeholders?: string[];
  createdAt?: string;
  updatedAt?: string;
}

function fromApiWorkflowTemplate(api: ApiWorkflowTemplateSummary): WorkflowTemplateSummary {
  return {
    template_id: api.templateId ?? '',
    display_name: api.displayName ?? '',
    script_hash: api.scriptHash ?? '',
    trust_latch: api.trustLatch ?? false,
    required_agent_types: api.requiredAgentTypes ?? [],
    placeholders: api.placeholders ?? [],
    created_at: api.createdAt ?? '',
    updated_at: api.updatedAt ?? '',
  };
}

export async function fetchWorkflowTemplates(): Promise<WorkflowTemplateListResponse> {
  const data = await apiRequest<{ templates?: ApiWorkflowTemplateSummary[] }>('/workflow-templates');
  return { templates: (data.templates ?? []).map(fromApiWorkflowTemplate) };
}

export async function fetchWorkflowTemplateDetail(
  templateId: string,
): Promise<WorkflowTemplateDetailResponse> {
  const data = await apiRequest<{
    template?: ApiWorkflowTemplateSummary;
    scriptCode?: string;
    boundCronCount?: number;
  }>(`/workflow-templates/${encodeURIComponent(templateId)}`);
  return {
    template: fromApiWorkflowTemplate(data.template ?? {}),
    script_code: data.scriptCode ?? '',
    bound_cron_count: data.boundCronCount ?? 0,
  };
}

export async function saveWorkflowTemplateFromRun(
  payload: SaveWorkflowTemplateFromRunPayload,
): Promise<WorkflowTemplateSummary> {
  const data = await apiRequest<ApiWorkflowTemplateSummary>('/workflow-templates/from-run', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return fromApiWorkflowTemplate(data ?? {});
}

export async function upsertWorkflowTemplate(
  templateId: string,
  payload: UpsertWorkflowTemplatePayload,
): Promise<WorkflowTemplateSummary> {
  const data = await apiRequest<ApiWorkflowTemplateSummary>(
    `/workflow-templates/${encodeURIComponent(templateId)}`,
    {
      method: 'PUT',
      body: JSON.stringify({
        displayName: payload.display_name,
        scriptCode: payload.script_code,
        trustLatch: payload.trust_latch ?? false,
      }),
    },
  );
  return fromApiWorkflowTemplate(data ?? {});
}

export async function deleteWorkflowTemplate(templateId: string): Promise<{ deleted: boolean }> {
  return apiRequest(`/workflow-templates/${encodeURIComponent(templateId)}`, {
    method: 'DELETE',
  });
}
