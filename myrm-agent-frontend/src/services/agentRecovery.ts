/**
 * [INPUT]
 * - @/lib/api/apiClient::apiRequest
 *
 * [OUTPUT]
 * - fetchProfileRecoveryHealth: 探针检测 Profile 组件健康状态
 * - rollbackProfileToLastKnownGood: 回滚到 Last-Known-Good 快照
 * - exportProfileRecoveryDiagnostics: 导出恢复排障诊断包
 *
 * [POS]
 * Agent Profile 启动期容灾自愈与回滚 API 客户端服务。
 */

import { apiRequest } from '@/lib/api';

export interface ComponentProbe {
  component_type: string;
  component_id: string;
  status: 'healthy' | 'quarantined' | 'error';
  error_message?: string | null;
}

export interface ProfileRecoveryHealthReport {
  agent_id: string;
  is_healthy: boolean;
  healthy_components: ComponentProbe[];
  quarantined_components: ComponentProbe[];
  has_last_known_good: boolean;
  last_known_good_id?: string | null;
  timestamp: string;
}

export interface ProfileRecoveryDiagnostics {
  agent_id: string;
  exported_at: string;
  health_report: {
    is_healthy: boolean;
    healthy_count: number;
    quarantined_count: number;
    healthy_components: ComponentProbe[];
    quarantined_components: ComponentProbe[];
    has_last_known_good: boolean;
    last_known_good_id?: string | null;
  };
  recent_snapshots: Array<{
    id: string;
    reason: string;
    created_at: string | null;
  }>;
}

export const fetchProfileRecoveryHealth = async (agentId: string): Promise<ProfileRecoveryHealthReport> => {
  const data = (await apiRequest(`/user-agents/agents/${agentId}/recovery/health`)) as ProfileRecoveryHealthReport;
  return data;
};

export const rollbackProfileToLastKnownGood = async (agentId: string): Promise<boolean> => {
  const data = (await apiRequest(`/user-agents/agents/${agentId}/recovery/rollback`, {
    method: 'POST',
  })) as { rolled_back: boolean };
  return Boolean(data.rolled_back);
};

export const exportProfileRecoveryDiagnostics = async (agentId: string): Promise<ProfileRecoveryDiagnostics> => {
  const data = (await apiRequest(`/user-agents/agents/${agentId}/recovery/diagnostics`)) as {
    diagnostics: ProfileRecoveryDiagnostics;
  };
  return data.diagnostics;
};
