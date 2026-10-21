export type DegradationSeverity = 'info' | 'warning' | 'degraded' | 'critical';

export type DependencyComponentType =
  | 'model'
  | 'search'
  | 'sandbox'
  | 'knowledge_base'
  | 'external_api';

export type CircuitBreakerStatus = 'closed' | 'half_open' | 'open';

export interface ComponentHealthRecord {
  id: string;
  name: string;
  type: DependencyComponentType;
  status: CircuitBreakerStatus;
  latencyMs: number;
  errorRatePercent: number; // 0 - 100
  lastCheckedAt: number;
  failureReason?: string;
  fallbackStrategy: string;
}

export interface DegradationEvent {
  id: string;
  componentId: string;
  componentName: string;
  severity: DegradationSeverity;
  title: string;
  explanation: string;
  fallbackActive: boolean;
  fallbackActionLabel: string;
  recoveryEtaSec?: number;
  timestamp: number;
}

export type GlobalSystemHealthStatus = 'healthy' | 'degraded' | 'maintenance';

export interface SystemHealthSummary {
  overallStatus: GlobalSystemHealthStatus;
  healthyCount: number;
  degradedCount: number;
  openBreakerCount: number;
  averageLatencyMs: number;
  healthScore: number; // 0 - 100
}
