import type { AuditLogEvent, AuditLogStats } from './types';

export function mapAuditLogEvent(log: Record<string, unknown>): AuditLogEvent {
  return {
    event_type: String(log.eventType ?? log.event_type ?? ''),
    timestamp: String(log.timestamp ?? ''),
    severity: String(log.severity ?? 'info'),
    user_id: (log.userId ?? log.user_id ?? null) as string | null,
    sandbox_id: (log.sandboxId ?? log.sandbox_id ?? null) as string | null,
    resource: (log.resource ?? null) as string | null,
    action: String(log.action ?? ''),
    result: String(log.result ?? ''),
    metadata: (typeof log.metadata === 'object' && log.metadata !== null
      ? log.metadata
      : {}) as Record<string, unknown>,
    ip_address: (log.ipAddress ?? log.ip_address ?? null) as string | null,
    trace_id: (log.traceId ?? log.trace_id ?? null) as string | null,
    request_id: (log.requestId ?? log.request_id ?? null) as string | null,
    traffic_class: (log.trafficClass ?? log.traffic_class ?? null) as string | null,
  };
}

export function mapAuditStatsResponse(result: Record<string, unknown>): AuditLogStats {
  const successFailed = (result.successVsFailed ?? result.success_vs_failed ?? {}) as Record<
    string,
    unknown
  >;

  return {
    time_series: Array.isArray(result.timeSeries)
      ? result.timeSeries.map((item: Record<string, unknown>) => ({
          timestamp: String(item.timestamp ?? ''),
          total: Number(item.total ?? 0),
          success: Number(item.success ?? 0),
          failed: Number(item.failed ?? 0),
        }))
      : Array.isArray(result.time_series)
        ? (result.time_series as AuditLogStats['time_series'])
        : [],
    top_ips: (result.topIps ?? result.top_ips ?? []).map((item: Record<string, unknown>) => ({
      ip_address: String(item.ipAddress ?? item.ip_address ?? ''),
      request_count: Number(item.requestCount ?? item.request_count ?? 0),
    })),
    event_distribution: (result.eventDistribution ?? result.event_distribution ?? []).map(
      (item: Record<string, unknown>) => ({
        event_type: String(item.eventType ?? item.event_type ?? ''),
        count: Number(item.count ?? 0),
      }),
    ),
    success_vs_failed: {
      success: Number(successFailed.success ?? 0),
      failed: Number(successFailed.failed ?? 0),
    },
    total_events: Number(result.totalEvents ?? result.total_events ?? 0),
    time_range_hours: Number(result.timeRangeHours ?? result.time_range_hours ?? 24),
  };
}
