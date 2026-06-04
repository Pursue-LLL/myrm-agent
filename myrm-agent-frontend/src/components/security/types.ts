export interface SecurityMetrics {
  totalAlerts: number;
  criticalCount: number;
  highCount: number;
  mediumCount: number;
  lowCount: number;
  openDependabotPrs: number;
  securityPrs: number;
}

export interface SecurityAlert {
  id: number;
  severity: string;
  ruleId: string;
  ruleDescription: string;
  state: string;
  createdAt: string;
  htmlUrl: string;
}

export interface DependabotPR {
  number: number;
  title: string;
  state: string;
  labels: string[];
  htmlUrl: string;
  createdAt: string;
}

export interface SecurityDashboardData {
  metrics: SecurityMetrics;
  recentAlerts: SecurityAlert[];
  recentPrs: DependabotPR[];
  sbomAvailable: boolean;
  dataSource?: 'github' | 'control_plane' | 'merged';
}

export interface SecuritySetupHints {
  deployMode: string;
  isSandbox: boolean;
  cpIngressConfigured: boolean;
  githubTokenConfigured: boolean;
  webhookTenantId: string | null;
  webhookUrl: string | null;
  cpWebhookSecretEnv: string;
}

export interface RateLimitStatus {
  userId: string;
  resource: string;
  current: number;
  max: number;
  remaining: number;
  windowSeconds: number;
}

export interface AuditLogEvent {
  event_type: string;
  timestamp: string;
  severity: string;
  user_id: string | null;
  sandbox_id: string | null;
  resource: string | null;
  action: string;
  result: string;
  metadata: Record<string, unknown>;
  ip_address: string | null;
  trace_id: string | null;
  request_id: string | null;
  traffic_class: string | null;
}

export interface AuditLogStats {
  time_series: Array<{
    timestamp: string;
    total: number;
    success: number;
    failed: number;
  }>;
  top_ips: Array<{
    ip_address: string;
    request_count: number;
  }>;
  event_distribution: Array<{
    event_type: string;
    count: number;
  }>;
  success_vs_failed: {
    success: number;
    failed: number;
  };
  total_events: number;
  time_range_hours: number;
}

export type SecurityTabType = 'dependencies' | 'rate-limit' | 'audit-logs' | 'audit-stats';
