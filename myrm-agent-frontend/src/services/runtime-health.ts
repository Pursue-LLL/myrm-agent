import { apiRequest } from '@/lib/api';

export type HealthStatus = 'pass' | 'warn' | 'fail';
export type RepairRiskLevel = 'low' | 'medium' | 'high';
export type RepairScope = 'current_runtime' | 'current_workspace' | 'integration' | 'platform_sandbox';

export interface HealthReport {
  component_name: string;
  status: HealthStatus;
  message: string;
  code?: string | null;
  meta_data?: Record<string, unknown> | null;
  detail?: string | null;
  fix_suggestion?: string | null;
}

export interface RepairAction {
  action_id: string;
  title: string;
  description: string;
  component: string;
  layer: string;
  scope: RepairScope;
  risk_level: RepairRiskLevel;
  requires_approval: boolean;
  dry_run_supported: boolean;
  executable: boolean;
  method?: string | null;
  endpoint?: string | null;
  confirm_required: boolean;
  reason: string;
  expected_effect: string;
  does_not_do: string[];
}

export interface DoctorResponse {
  server: HealthReport[];
  harness: HealthReport[];
  repair_actions: RepairAction[];
}

export interface RepairActionExecuteRequest {
  dry_run: boolean;
  confirm: boolean;
}

export interface RepairActionExecuteResult {
  action_id: string;
  status: string;
  changed: boolean;
  dry_run: boolean;
  message: string;
  details: Record<string, unknown>;
}

export async function getRuntimeDoctor(): Promise<DoctorResponse> {
  return apiRequest<DoctorResponse>('/health/doctor');
}

export async function executeRepairAction(
  actionId: string,
  request: RepairActionExecuteRequest,
): Promise<RepairActionExecuteResult> {
  return apiRequest<RepairActionExecuteResult>(`/health/repair-actions/${actionId}/execute`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}
