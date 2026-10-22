/**
 * [INPUT]
 * - 纯 TypeScript 类型定义，用于 Cron 自动化任务舰队健康体检与外科手术式修复
 *
 * [OUTPUT]
 * - CronHealthIssueCategory, CronJobHealthIssue, CronFleetDoctorReport, QuickFixRequest, QuickFixResponse
 *
 * [POS]
 * src/components/features/system-monitor/cronDoctorTypes.ts — 定时任务舰队体检医生契约
 */

export type CronHealthIssueCategory =
  | 'execution_failed'
  | 'delivery_failed'
  | 'delivery_unverified'
  | 'schedule_overdue'
  | 'script_not_found'
  | 'workdir_not_found';

export type CronIssueSeverity = 'critical' | 'warning' | 'info';

export interface CronJobHealthIssue {
  job_id: string;
  job_name: string;
  category: CronHealthIssueCategory | string;
  severity: CronIssueSeverity | string;
  message: string;
  suggested_fix: string;
  details?: Record<string, string>;
  can_quick_fix?: boolean;
}

export interface CronFleetDoctorReport {
  total_jobs: number;
  healthy_jobs_count: number;
  issues_count: number;
  is_fleet_healthy: boolean;
  issues: CronJobHealthIssue[];
  inspected_at: string;
}

export interface QuickFixRequest {
  issue_category: string;
  remediation_param?: string;
}

export interface QuickFixResponse {
  job_id: string;
  fixed_category: string;
  status: string;
  message: string;
  remediated_at: string;
}
