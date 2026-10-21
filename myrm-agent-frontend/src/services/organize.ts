import { apiRequest } from '@/lib/api';
import type { OrganizeApplyResponse, OrganizeLatestJobResponse, OrganizePlanDto } from './organizeTypes';

export async function applyOrganizePlan(
  workspace: string,
  plan: OrganizePlanDto,
  dryRun: boolean,
): Promise<OrganizeApplyResponse> {
  const query = dryRun ? '?dryRun=true' : '?dryRun=false';
  return apiRequest<OrganizeApplyResponse>(`/files/organize/apply${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace, plan }),
  });
}

export async function rollbackOrganizeJob(jobId: string): Promise<OrganizeApplyResponse> {
  return apiRequest<OrganizeApplyResponse>(`/files/organize/rollback/${encodeURIComponent(jobId)}`, {
    method: 'POST',
  });
}

export async function fetchLatestOrganizeJob(workspace: string): Promise<OrganizeLatestJobResponse> {
  const params = new URLSearchParams({ workspace });
  return apiRequest<OrganizeLatestJobResponse>(`/files/organize/latest-job?${params}`);
}
