/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: HTTP client wrapper)
 *
 * [OUTPUT]
 * - FleetNodeState: 六态状态类型定义
 * - ProbeStageResultDTO: 单阶段探针结果 DTO
 * - FleetDiagnosisResponse: 节点六态精细化诊断报告 DTO
 * - FleetHealthSummaryResponse: 机队健康六态分布概览 DTO
 * - diagnoseFleetNode: 执行五级自省探针诊断 API
 * - getFleetHealthSummary: 获取机队六态健康分布概览 API
 *
 * [POS]
 * 前端机队健康遥测与配额诊断服务层。向后端请求五级自省探针排障与六态健康概览。
 */

import { apiRequest } from '@/lib/api';

export type FleetNodeState =
  | 'online'
  | 'offline'
  | 'misconfigured'
  | 'provider_unavailable'
  | 'gateway_stopped'
  | 'runner_broken';

export interface ProbeStageResultDTO {
  stage: string;
  passed: boolean;
  latency_ms: number;
  message: string;
  details?: Record<string, unknown>;
}

export interface FleetDiagnosisResponse {
  node_id: string;
  node_name: string;
  state: FleetNodeState;
  root_cause: string;
  recommended_action: string;
  stages: ProbeStageResultDTO[];
  diagnosed_at: number;
}

export interface FleetHealthSummaryResponse {
  total_nodes: number;
  online_count: number;
  offline_count: number;
  misconfigured_count: number;
  provider_unavailable_count: number;
  gateway_stopped_count: number;
  runner_broken_count: number;
  quota_healthy: boolean;
}

export interface FleetDiagnoseParams {
  node_id: string;
  node_name: string;
  host: string;
  port?: number;
  token?: string;
  provider_name?: string;
  model_name?: string;
}

/**
 * 执行指定分布式节点的五级渐进式自省探针诊断。
 */
export async function diagnoseFleetNode(
  params: FleetDiagnoseParams
): Promise<FleetDiagnosisResponse> {
  return apiRequest<FleetDiagnosisResponse>('/agents/fleet/diagnose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
}

/**
 * 获取机队节点六态分布概览。
 */
export async function getFleetHealthSummary(): Promise<FleetHealthSummaryResponse> {
  return apiRequest<FleetHealthSummaryResponse>('/agents/fleet/health-summary', {
    silent: true,
  });
}
