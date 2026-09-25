import { ApiError, apiRequest } from '@/lib/api';

export interface WorkflowTemplateSummary {
  template_id: string;
  display_name: string;
  script_hash: string;
  trust_latch: boolean;
  required_agent_types: string[];
  placeholders: string[];
  is_trunk: boolean;
  created_at: string;
  updated_at: string;
}

export interface AdmitHandoffMaterial {
  title: string;
  excerpt: string;
}

export interface AdmitHandoff {
  source_flow: string;
  target_flow: string;
  intent: string;
  materials?: AdmitHandoffMaterial[];
  evidence_refs?: string[];
}

export interface AdmitTemplateRunPayload {
  template_args?: Record<string, string> | null;
  handoff?: AdmitHandoff | null;
  prior_criteria?: string[] | null;
  prior_deliverable?: string | null;
}

export interface AdmitTemplateRunResult {
  admitted: boolean;
  template_id: string;
  reason_code: string;
  user_message: string;
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
  isTrunk?: boolean;
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
    is_trunk: api.isTrunk ?? false,
    created_at: api.createdAt ?? '',
    updated_at: api.updatedAt ?? '',
  };
}

interface ApiAdmitTemplateRunResult {
  admitted?: boolean;
  templateId?: string;
  reasonCode?: string;
  userMessage?: string;
}

export async function admitTemplateRun(
  templateId: string,
  payload: AdmitTemplateRunPayload,
): Promise<AdmitTemplateRunResult> {
  try {
    const data = await apiRequest<ApiAdmitTemplateRunResult>(
      `/workflow-templates/${encodeURIComponent(templateId)}/admit`,
      {
        method: 'POST',
        body: JSON.stringify({
          templateArgs: payload.template_args ?? null,
          handoff: payload.handoff
            ? {
                sourceFlow: payload.handoff.source_flow,
                targetFlow: payload.handoff.target_flow,
                intent: payload.handoff.intent,
                materials: payload.handoff.materials ?? [],
                evidenceRefs: payload.handoff.evidence_refs ?? [],
              }
            : null,
          priorCriteria: payload.prior_criteria ?? null,
          priorDeliverable: payload.prior_deliverable ?? null,
        }),
      },
    );
    return {
      admitted: data?.admitted ?? false,
      template_id: data?.templateId ?? templateId,
      reason_code: data?.reasonCode ?? 'UNKNOWN',
      user_message: data?.userMessage ?? '',
    };
  } catch (err) {
    // Gate denials arrive as 422 with {reason_code, message}: surface them as
    // data, not exceptions, so callers can show friendly copy.
    if (err instanceof ApiError) {
      const detail = (err.data ?? {}) as { reason_code?: unknown; message?: unknown };
      if (typeof detail.reason_code === 'string') {
        return {
          admitted: false,
          template_id: templateId,
          reason_code: detail.reason_code,
          user_message: typeof detail.message === 'string' ? detail.message : '',
        };
      }
    }
    throw err;
  }
}

export async function fetchWorkflowTemplates(): Promise<WorkflowTemplateListResponse> {
  const data = await apiRequest<{ templates?: ApiWorkflowTemplateSummary[] }>('/workflow-templates');
  return { templates: (data.templates ?? []).map(fromApiWorkflowTemplate) };
}

let trunkCatalogPromise: Promise<WorkflowTemplateSummary[]> | null = null;

/** Session-cached trunk subset for suggestion UIs (single network call). */
export function fetchTrunkCatalog(): Promise<WorkflowTemplateSummary[]> {
  if (!trunkCatalogPromise) {
    trunkCatalogPromise = fetchWorkflowTemplates()
      .then((response) => response.templates.filter((template) => template.is_trunk))
      .catch(() => []);
  }
  return trunkCatalogPromise;
}

export async function fetchWorkflowTemplateDetail(templateId: string): Promise<WorkflowTemplateDetailResponse> {
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
  const data = await apiRequest<ApiWorkflowTemplateSummary>(`/workflow-templates/${encodeURIComponent(templateId)}`, {
    method: 'PUT',
    body: JSON.stringify({
      displayName: payload.display_name,
      scriptCode: payload.script_code,
      trustLatch: payload.trust_latch ?? false,
    }),
  });
  return fromApiWorkflowTemplate(data ?? {});
}

export async function deleteWorkflowTemplate(templateId: string): Promise<{ deleted: boolean }> {
  return apiRequest(`/workflow-templates/${encodeURIComponent(templateId)}`, {
    method: 'DELETE',
  });
}
