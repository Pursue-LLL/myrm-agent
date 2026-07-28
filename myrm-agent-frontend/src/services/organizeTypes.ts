export interface OrganizePlanItemDto {
  src: string;
  dst: string;
  reason: string;
  src_mtime_ns?: number | null;
}

export interface OrganizePlanDto {
  version: 1;
  scope_root: string;
  preset: 'date' | 'ext' | 'project' | 'custom';
  items: OrganizePlanItemDto[];
}

export interface OrganizeApplyResponse {
  dryRun: boolean;
  ok: boolean;
  jobId?: string | null;
  jobStatus?: string | null;
  appliedCount?: number;
  moves?: Array<{ src: string; dst: string }>;
  issues?: Array<{ index: number; code: string; message: string }>;
}

export interface OrganizeLatestJobResponse {
  job: {
    jobId: string;
    status: string;
    appliedCount: number;
    createdAt: number;
  } | null;
}
