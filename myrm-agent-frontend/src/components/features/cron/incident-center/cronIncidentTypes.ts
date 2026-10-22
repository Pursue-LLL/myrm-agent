/**
 * Cron Incident & Silent Failure Verification Barrier Types
 * 定时任务事故待办中心与假成功静默失败门禁类型系统
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any；
 * 2. 强类型化状态机与断言边界；
 * 3. 行数严格控制在 400 行以内。
 */

export type IncidentCategory =
  | 'silent_failure' // 进程 exit 0 假成功，实际未产出交付物
  | 'timeout'        // 超时挂死中断
  | 'quota_exhausted'// 429 额度用尽
  | 'auth_expired'   // 401 密钥失效
  | 'runtime_crash';  // 非 0 退出崩溃

export type IncidentSeverity = 'critical' | 'warning' | 'info';

export interface ArtifactFileDescriptor {
  name: string;
  bytes: number;
  path?: string;
}

export interface ArtifactAcceptanceCriteria {
  minOutputBytes?: number;
  requiredArtifacts?: string[];
  contentKeywords?: string[];
  allowZeroByteIfNoError?: boolean;
}

export interface TaskExecutionRun {
  runId: string;
  jobId: string;
  jobName: string;
  exitCode: number;
  durationMs: number;
  stdout: string;
  stderr: string;
  generatedArtifacts: ArtifactFileDescriptor[];
  executedAt: string;
}

export interface AcceptanceVerificationResult {
  passed: boolean;
  isSilentFailure: boolean;
  reasons: string[];
  missingArtifacts: string[];
  missingKeywords: string[];
  actualBytes: number;
}

export interface CronIncident {
  id: string;
  jobId: string;
  jobName: string;
  runId: string;
  category: IncidentCategory;
  severity: IncidentSeverity;
  occurredAt: string;
  exitCode: number;
  summary: string;
  failureReason: string;
  verificationDetails?: AcceptanceVerificationResult;
  acknowledged: boolean;
  acknowledgedAt?: string;
  retryCount: number;
}

export interface IncidentMetrics {
  totalCount: number;
  unacknowledgedCount: number;
  silentFailureCount: number;
  criticalCount: number;
  hasBlockingIncidents: boolean;
}
