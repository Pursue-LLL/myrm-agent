'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import {
  Shield,
  AlertTriangle,
  CheckCircle,
  ExternalLink,
  GitPullRequest,
  Activity,
  FileText,
  Download,
} from 'lucide-react';
import { localizeReactNode } from '@/lib/utils/localeText';

interface SecurityMetrics {
  totalAlerts: number;
  criticalCount: number;
  highCount: number;
  mediumCount: number;
  lowCount: number;
  openDependabotPrs: number;
  securityPrs: number;
}

interface SecurityAlert {
  id: number;
  severity: string;
  ruleId: string;
  ruleDescription: string;
  state: string;
  createdAt: string;
  htmlUrl: string;
}

interface DependabotPR {
  number: number;
  title: string;
  state: string;
  labels: string[];
  htmlUrl: string;
  createdAt: string;
}

interface SecurityDashboardData {
  metrics: SecurityMetrics;
  recentAlerts: SecurityAlert[];
  recentPrs: DependabotPR[];
  sbomAvailable: boolean;
  dataSource?: 'github' | 'control_plane' | 'merged';
}

interface SecuritySetupHints {
  deployMode: string;
  isSandbox: boolean;
  cpIngressConfigured: boolean;
  githubTokenConfigured: boolean;
  webhookTenantId: string | null;
  webhookUrl: string | null;
  cpWebhookSecretEnv: string;
}

interface RateLimitStatus {
  userId: string;
  resource: string;
  current: number;
  max: number;
  remaining: number;
  windowSeconds: number;
}

interface AuditLogEvent {
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

interface AuditLogStats {
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

type TabType = 'dependencies' | 'rate-limit' | 'audit-logs' | 'audit-stats';

const SeverityBadge = ({ severity }: { severity: string }) => {
  const colors = {
    critical: 'bg-red-500/10 text-red-500 border-red-500/20',
    high: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
    medium: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
    low: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  };

  return (
    <span
      className={`px-2 py-1 text-xs font-medium rounded border ${colors[severity as keyof typeof colors] || colors.low}`}
    >
      {severity.toUpperCase()}
    </span>
  );
};

const MetricCard = ({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string;
  value: number;
  icon: any;
  color: string;
}) => (
  <div className={`rounded-lg border p-4 ${color}`}>
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm text-muted-foreground">{title}</p>
        <p className="text-3xl font-bold mt-1">{value}</p>
      </div>
      <Icon className="w-8 h-8 opacity-50" />
    </div>
  </div>
);

export default function SecurityDashboard() {
  const t = useTranslations('securityDashboard');
  const [activeTab, setActiveTab] = useState<TabType>('dependencies');
  const [data, setData] = useState<SecurityDashboardData | null>(null);
  const [setupHints, setSetupHints] = useState<SecuritySetupHints | null>(null);
  const [rateLimitLive, setRateLimitLive] = useState(false);
  const [rateLimitData, setRateLimitData] = useState<RateLimitStatus[]>([]);
  const [urlCopied, setUrlCopied] = useState(false);
  const [auditLogData, setAuditLogData] = useState<AuditLogEvent[]>([]);
  const [filteredAuditLogData, setFilteredAuditLogData] = useState<AuditLogEvent[]>([]);
  const [auditStatsData, setAuditStatsData] = useState<AuditLogStats | null>(null);
  const [auditLive, setAuditLive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchUserId, setSearchUserId] = useState('');
  const [searchEventType, setSearchEventType] = useState('');
  const [searchResult, setSearchResult] = useState<'all' | 'success' | 'failed'>('all');

  const fetchSetupHints = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/security/setup-hints');
      if (response.ok) {
        const result = await response.json();
        setSetupHints(result);
      }
    } catch (err) {
      console.error('Failed to fetch security setup hints:', err);
    }
  }, []);

  useEffect(() => {
    fetchSetupHints();
  }, [fetchSetupHints]);

  useEffect(() => {
    if (activeTab === 'dependencies') {
      fetchSecurityData();
    } else if (activeTab === 'rate-limit') {
      fetchRateLimitData();
    } else if (activeTab === 'audit-logs') {
      fetchAuditLogData();
    } else if (activeTab === 'audit-stats') {
      fetchAuditStatsData();
    }
  }, [activeTab]);

  useEffect(() => {
    if (auditLogData.length === 0) {
      setFilteredAuditLogData([]);
      return;
    }

    let filtered = auditLogData;

    if (searchUserId) {
      filtered = filtered.filter((event) => event.user_id?.toLowerCase().includes(searchUserId.toLowerCase()));
    }

    if (searchEventType) {
      filtered = filtered.filter((event) => event.event_type.toLowerCase().includes(searchEventType.toLowerCase()));
    }

    if (searchResult !== 'all') {
      if (searchResult === 'success') {
        filtered = filtered.filter((event) => event.result === 'success');
      } else if (searchResult === 'failed') {
        filtered = filtered.filter((event) => event.result !== 'success');
      }
    }

    setFilteredAuditLogData(filtered);
  }, [auditLogData, searchUserId, searchEventType, searchResult]);

  const fetchSecurityData = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/security/dashboard');

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      setData(result);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch security data:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const fetchRateLimitData = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/security/rate-limits');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      const result = await response.json();
      setRateLimitData(Array.isArray(result.items) ? result.items : []);
      setRateLimitLive(Boolean(result.isLive));
      setError(null);
    } catch (err) {
      console.error('Failed to fetch rate limit data:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const dataSourceLabel = (source: SecurityDashboardData['dataSource']) => {
    if (source === 'merged') return t('dataSourceMerged');
    if (source === 'control_plane') return t('dataSourceCp');
    return t('dataSourceGithub');
  };

  const copyWebhookUrl = async () => {
    if (!setupHints?.webhookUrl) return;
    await navigator.clipboard.writeText(setupHints.webhookUrl);
    setUrlCopied(true);
    setTimeout(() => setUrlCopied(false), 2000);
  };

  const fetchAuditLogData = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/security/audit/logs?limit=100');

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      const rawEvents = Array.isArray(result.events) ? result.events : [];
      const transformedLogs: AuditLogEvent[] = rawEvents.map((log: Record<string, unknown>) => ({
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
      }));
      setAuditLogData(transformedLogs);
      setAuditLive(Boolean(result.isLive));
      setError(null);
    } catch (err) {
      console.error('Failed to fetch audit log data:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const fetchAuditStatsData = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/security/audit/stats?hours=24');

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      const successFailed = result.successVsFailed ?? result.success_vs_failed ?? {};

      const stats: AuditLogStats = {
        time_series: Array.isArray(result.timeSeries)
          ? result.timeSeries.map((item: Record<string, unknown>) => ({
              timestamp: String(item.timestamp ?? ''),
              total: Number(item.total ?? 0),
              success: Number(item.success ?? 0),
              failed: Number(item.failed ?? 0),
            }))
          : Array.isArray(result.time_series)
            ? result.time_series
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
      setAuditStatsData(stats);
      setAuditLive(Boolean(result.isLive));
      setError(null);
    } catch (err) {
      console.error('Failed to fetch audit stats data:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const exportAuditLogs = async (format: 'csv' | 'json') => {
    try {
      const response = await fetch(`/api/v1/security/audit/export?format=${format}`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const blob = await response.blob();
      const filename = `auth_audit_logs_${new Date().toISOString().split('T')[0]}.${format}`;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Failed to export audit logs:', err);
      setError(err instanceof Error ? err.message : 'Export failed');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-red-500">{t('loadFailed')}</h3>
            <p className="text-sm text-muted-foreground mt-1">{error}</p>
            <button onClick={fetchSecurityData} className="mt-2 text-sm text-primary hover:underline">
              {t('retry')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const tabs = [
    { id: 'dependencies' as TabType, label: t('tabDependencies'), icon: Shield },
    { id: 'rate-limit' as TabType, label: t('tabRateLimit'), icon: Activity },
    { id: 'audit-logs' as TabType, label: t('tabAuditLogs'), icon: FileText },
    { id: 'audit-stats' as TabType, label: t('tabAuditStats'), icon: Activity },
  ];

  return localizeReactNode(
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Shield className="w-8 h-8" />
            {t('title')}
          </h1>
          <p className="text-muted-foreground mt-1">{t('subtitle')}</p>
          {data?.dataSource && (
            <p className="text-xs text-muted-foreground mt-2">
              {dataSourceLabel(data.dataSource)}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {activeTab === 'audit-logs' && (
            <>
              <button
                onClick={() => exportAuditLogs('csv')}
                className="px-4 py-2 rounded-lg border hover:bg-accent transition-colors flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                {t('auditExportCsv')}
              </button>
              <button
                onClick={() => exportAuditLogs('json')}
                className="px-4 py-2 rounded-lg border hover:bg-accent transition-colors flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                {t('auditExportJson')}
              </button>
            </>
          )}
          <button
            onClick={() => {
              if (activeTab === 'dependencies') fetchSecurityData();
              else if (activeTab === 'rate-limit') fetchRateLimitData();
              else if (activeTab === 'audit-logs') fetchAuditLogData();
              else if (activeTab === 'audit-stats') fetchAuditStatsData();
            }}
            className="px-4 py-2 rounded-lg border hover:bg-accent transition-colors"
          >
            {t('refresh')}
          </button>
        </div>
      </div>

      {setupHints?.isSandbox && (
        <div className="rounded-xl border border-primary/25 bg-gradient-to-br from-primary/8 via-background to-background p-4 md:p-6 space-y-3 shadow-sm">
          <h2 className="text-lg font-semibold">{t('setupTitle')}</h2>
          {!setupHints.cpIngressConfigured && (
            <p className="text-sm text-amber-600 dark:text-amber-400">{t('noIngress')}</p>
          )}
          {setupHints.webhookTenantId && (
            <p className="text-sm text-muted-foreground">
              {t('setupTenant')}: <span className="font-mono">{setupHints.webhookTenantId}</span>
            </p>
          )}
          {setupHints.webhookUrl && (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="flex-1 min-w-0">
                <p className="text-xs text-muted-foreground mb-1">{t('setupUrl')}</p>
                <code className="text-xs break-all block p-2 rounded bg-background border">
                  {setupHints.webhookUrl}
                </code>
              </div>
              <button
                type="button"
                onClick={copyWebhookUrl}
                className="px-3 py-2 text-sm rounded-lg border hover:bg-accent shrink-0"
              >
                {urlCopied ? t('copied') : t('copyUrl')}
              </button>
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            {t('setupSecret', { env: setupHints.cpWebhookSecretEnv })}
          </p>
          {!setupHints.githubTokenConfigured && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              {t('setupToken')}{' '}
              <Link href="/settings/credentials" className="text-primary underline underline-offset-2">
                {t('openSettingsCredentials')}
              </Link>
            </p>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b overflow-x-auto">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 font-medium transition-colors border-b-2 flex items-center gap-2 ${
                activeTab === tab.id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      {activeTab === 'dependencies' && data && (
        <>
          {/* Metrics Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              title={t('metricCritical')}
              value={data.metrics.criticalCount}
              icon={AlertTriangle}
              color="bg-red-500/5 border-red-500/20"
            />
            <MetricCard
              title={t('metricHigh')}
              value={data.metrics.highCount}
              icon={AlertTriangle}
              color="bg-orange-500/5 border-orange-500/20"
            />
            <MetricCard
              title={t('metricMedium')}
              value={data.metrics.mediumCount}
              icon={AlertTriangle}
              color="bg-yellow-500/5 border-yellow-500/20"
            />
            <MetricCard
              title={t('metricSecurityPrs')}
              value={data.metrics.securityPrs}
              icon={GitPullRequest}
              color="bg-green-500/5 border-green-500/20"
            />
          </div>

          {/* Recent Alerts */}
          <div className="rounded-lg border p-6">
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5" />
              {t('recentAlertsTitle')}
            </h2>

            {data.recentAlerts.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <CheckCircle className="w-12 h-12 mx-auto mb-2 text-green-500" />
                <p>{t('noAlerts')}</p>
              </div>
            ) : (
              <div className="space-y-3">
                {data.recentAlerts.map((alert) => (
                  <div
                    key={alert.id}
                    className="flex items-start justify-between p-3 rounded-lg border hover:bg-accent transition-colors"
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <SeverityBadge severity={alert.severity} />
                        <span className="text-sm text-muted-foreground">
                          {new Date(alert.createdAt).toLocaleDateString()}
                        </span>
                      </div>
                      <p className="font-medium">{alert.ruleDescription}</p>
                      <p className="text-sm text-muted-foreground mt-1">Rule: {alert.ruleId}</p>
                    </div>
                    <a
                      href={alert.htmlUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-sm text-primary hover:underline flex-shrink-0"
                    >
                      {t('viewOnGithub')}
                      <ExternalLink className="w-4 h-4" />
                    </a>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Dependabot PRs */}
          <div className="rounded-lg border p-6">
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
              <GitPullRequest className="w-5 h-5" />
              {t('dependabotPrsTitle')} ({data.metrics.openDependabotPrs})
            </h2>

            {data.recentPrs.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <CheckCircle className="w-12 h-12 mx-auto mb-2 text-green-500" />
                <p>{t('allDepsUpToDate')}</p>
              </div>
            ) : (
              <div className="space-y-3">
                {data.recentPrs.map((pr) => (
                  <div
                    key={pr.number}
                    className="flex items-start justify-between p-3 rounded-lg border hover:bg-accent transition-colors"
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-medium text-muted-foreground">#{pr.number}</span>
                        {pr.labels.includes('security') && (
                          <span className="px-2 py-0.5 text-xs font-medium rounded bg-red-500/10 text-red-500 border border-red-500/20">
                            {t('securityLabel')}
                          </span>
                        )}
                      </div>
                      <p className="font-medium">{pr.title}</p>
                      <div className="flex items-center gap-2 mt-2">
                        {pr.labels.slice(0, 3).map((label) => (
                          <span key={label} className="px-2 py-0.5 text-xs rounded bg-primary/10 text-primary">
                            {label}
                          </span>
                        ))}
                      </div>
                    </div>
                    <a
                      href={pr.htmlUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-sm text-primary hover:underline flex-shrink-0"
                    >
                      {t('viewOnGithub')}
                      <ExternalLink className="w-4 h-4" />
                    </a>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {activeTab === 'rate-limit' && (
        <div className="rounded-lg border p-6">
          <div className="flex items-start justify-between mb-4">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Activity className="w-5 h-5" />
              {t('rateLimitMonitorTitle')}
            </h2>
            <div className="px-3 py-1 text-xs rounded-full bg-blue-500/10 text-blue-500 border border-blue-500/20">
              {rateLimitLive ? t('rateLimitLive') : t('rateLimitUnavailable')}
            </div>
          </div>

          {rateLimitData.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <CheckCircle className="w-12 h-12 mx-auto mb-2 text-green-500" />
              <p>{t('noRateLimits')}</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-3 px-4 font-medium text-sm text-muted-foreground">用户ID / User ID</th>
                    <th className="text-left py-3 px-4 font-medium text-sm text-muted-foreground">资源 / Resource</th>
                    <th className="text-right py-3 px-4 font-medium text-sm text-muted-foreground">当前 / Current</th>
                    <th className="text-right py-3 px-4 font-medium text-sm text-muted-foreground">最大 / Max</th>
                    <th className="text-right py-3 px-4 font-medium text-sm text-muted-foreground">剩余 / Remaining</th>
                    <th className="text-right py-3 px-4 font-medium text-sm text-muted-foreground">窗口 / Window</th>
                    <th className="text-right py-3 px-4 font-medium text-sm text-muted-foreground">使用率 / Usage</th>
                  </tr>
                </thead>
                <tbody>
                  {rateLimitData.map((status, idx) => {
                    const usagePercent = (status.current / status.max) * 100;
                    const isHigh = usagePercent > 80;

                    return (
                      <tr key={idx} className="border-b hover:bg-accent transition-colors">
                        <td className="py-3 px-4 font-mono text-sm">{status.userId}</td>
                        <td className="py-3 px-4 text-sm">{status.resource}</td>
                        <td className="py-3 px-4 text-right font-mono text-sm">{status.current}</td>
                        <td className="py-3 px-4 text-right font-mono text-sm">{status.max}</td>
                        <td className="py-3 px-4 text-right font-mono text-sm">
                          <span className={isHigh ? 'text-red-500 font-semibold' : ''}>{status.remaining}</span>
                        </td>
                        <td className="py-3 px-4 text-right text-sm text-muted-foreground">
                          {Math.floor(status.windowSeconds / 60)}min
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <div className="w-16 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                              <div
                                className={`h-full transition-all ${isHigh ? 'bg-red-500' : 'bg-green-500'}`}
                                style={{ width: `${Math.min(usagePercent, 100)}%` }}
                              />
                            </div>
                            <span
                              className={`text-xs font-medium ${isHigh ? 'text-red-500' : 'text-muted-foreground'}`}
                            >
                              {usagePercent.toFixed(0)}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 'audit-logs' && (
        <div className="rounded-lg border p-6">
          <div className="flex items-start justify-between mb-4">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <FileText className="w-5 h-5" />
              {t('auditLogsTitle')}
            </h2>
            <div
              className={`px-3 py-1 text-xs rounded-full border ${
                auditLive
                  ? 'bg-green-500/10 text-green-600 border-green-500/20'
                  : 'bg-muted text-muted-foreground border-border'
              }`}
            >
              {auditLive ? t('auditLive') : t('auditOffline')}
            </div>
          </div>

          {/* Search Filters */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4 p-4 rounded-lg bg-muted/50">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">{t('auditFilterUserId')}</label>
              <input
                type="text"
                value={searchUserId}
                onChange={(e) => setSearchUserId(e.target.value)}
                placeholder={t('auditFilterUserIdPlaceholder')}
                className="w-full px-3 py-2 text-sm rounded-full border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">{t('auditFilterEventType')}</label>
              <input
                type="text"
                value={searchEventType}
                onChange={(e) => setSearchEventType(e.target.value)}
                placeholder={t('auditFilterEventTypePlaceholder')}
                className="w-full px-3 py-2 text-sm rounded-full border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">{t('auditFilterResult')}</label>
              <select
                value={searchResult}
                onChange={(e) => setSearchResult(e.target.value as 'all' | 'success' | 'failed')}
                className="w-full px-3 py-2 text-sm rounded-full border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="all">{t('auditFilterAll')}</option>
                <option value="success">{t('auditFilterSuccess')}</option>
                <option value="failed">{t('auditFilterFailed')}</option>
              </select>
            </div>
          </div>

          <div className="text-xs text-muted-foreground mb-2">
            {t('auditShowingCount', { shown: filteredAuditLogData.length, total: auditLogData.length })}
          </div>

          {filteredAuditLogData.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <CheckCircle className="w-12 h-12 mx-auto mb-2 text-gray-400" />
              <p>{auditLogData.length > 0 ? t('auditNoMatch') : t('auditEmpty')}</p>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredAuditLogData.map((event, idx) => {
                const isSuccess = event.result === 'success';

                return (
                  <div
                    key={idx}
                    className={`p-3 rounded-lg border transition-colors ${
                      isSuccess ? 'hover:bg-green-500/5' : 'hover:bg-red-500/5'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span
                            className={`px-2 py-0.5 text-xs font-medium rounded border ${
                              isSuccess
                                ? 'bg-green-500/10 text-green-500 border-green-500/20'
                                : 'bg-red-500/10 text-red-500 border-red-500/20'
                            }`}
                          >
                            {event.event_type}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {new Date(event.timestamp).toLocaleString()}
                          </span>
                        </div>
                        <div className="text-sm space-y-1 mt-2">
                          {event.user_id && (
                            <p>
                              <span className="text-muted-foreground">User:</span>{' '}
                              <span className="font-mono">{event.user_id}</span>
                            </p>
                          )}
                          {event.ip_address && (
                            <p>
                              <span className="text-muted-foreground">IP:</span>{' '}
                              <span className="font-mono">{event.ip_address}</span>
                            </p>
                          )}
                          {event.action && (
                            <p>
                              <span className="text-muted-foreground">Action:</span> <span>{event.action}</span>
                            </p>
                          )}
                          {event.result && (
                            <p>
                              <span className="text-muted-foreground">Result:</span>{' '}
                              <span className={isSuccess ? 'text-green-500' : 'text-red-500'}>{event.result}</span>
                            </p>
                          )}
                          {event.metadata && Object.keys(event.metadata).length > 0 && (
                            <details className="mt-2">
                              <summary className="text-xs text-muted-foreground cursor-pointer hover:underline">
                                Metadata
                              </summary>
                              <pre className="text-xs bg-muted p-2 rounded mt-1 overflow-x-auto">
                                {JSON.stringify(event.metadata, null, 2)}
                              </pre>
                            </details>
                          )}
                        </div>
                      </div>
                      {event.trace_id && (
                        <div className="text-xs text-muted-foreground font-mono flex-shrink-0 ml-4">
                          trace: {event.trace_id.slice(0, 8)}...
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {activeTab === 'audit-stats' && auditStatsData && (
        <div className="rounded-lg border p-6">
          <div className="flex items-start justify-between mb-4">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Activity className="w-5 h-5" />
              {t('auditStatsTitle')}
            </h2>
            <div
              className={`px-3 py-1 text-xs rounded-full border ${
                auditLive
                  ? 'bg-green-500/10 text-green-600 border-green-500/20'
                  : 'bg-muted text-muted-foreground border-border'
              }`}
            >
              {auditLive ? t('auditLive') : t('auditOffline')}
            </div>
          </div>

          {/* Overall Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="p-4 rounded-lg border">
              <div className="text-sm text-muted-foreground">{t('auditTotalEvents')}</div>
              <div className="text-3xl font-bold mt-1">{auditStatsData.total_events}</div>
              <div className="text-xs text-muted-foreground mt-1">
                {t('auditLastHours', { hours: auditStatsData.time_range_hours })}
              </div>
            </div>
            <div className="p-4 rounded-lg border bg-green-500/5">
              <div className="text-sm text-muted-foreground">{t('auditSuccess')}</div>
              <div className="text-3xl font-bold mt-1 text-green-600">{auditStatsData.success_vs_failed.success}</div>
              <div className="text-xs text-muted-foreground mt-1">
                {auditStatsData.total_events > 0
                  ? `${((auditStatsData.success_vs_failed.success / auditStatsData.total_events) * 100).toFixed(1)}%`
                  : '0%'}
              </div>
            </div>
            <div className="p-4 rounded-lg border bg-red-500/5">
              <div className="text-sm text-muted-foreground">{t('auditFailed')}</div>
              <div className="text-3xl font-bold mt-1 text-red-600">{auditStatsData.success_vs_failed.failed}</div>
              <div className="text-xs text-muted-foreground mt-1">
                {auditStatsData.total_events > 0
                  ? `${((auditStatsData.success_vs_failed.failed / auditStatsData.total_events) * 100).toFixed(1)}%`
                  : '0%'}
              </div>
            </div>
          </div>

          {/* Time Series */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold mb-3">{t('auditTimeSeries')}</h3>
            <div className="space-y-2">
              {auditStatsData.time_series.map((point, idx) => {
                const total = point.total > 0 ? point.total : 1;
                return (
                <div key={idx} className="flex items-center gap-3">
                  <div className="text-sm text-muted-foreground w-40 flex-shrink-0">
                    {new Date(point.timestamp).toLocaleString(undefined, {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-8 bg-muted rounded-lg overflow-hidden flex">
                        <div
                          className="bg-green-500 flex items-center justify-center text-xs text-white font-medium"
                          style={{ width: `${(point.success / total) * 100}%` }}
                        >
                          {point.success > 0 && point.success}
                        </div>
                        <div
                          className="bg-red-500 flex items-center justify-center text-xs text-white font-medium"
                          style={{ width: `${(point.failed / total) * 100}%` }}
                        >
                          {point.failed > 0 && point.failed}
                        </div>
                      </div>
                      <div className="text-sm font-medium w-12 text-right">{point.total}</div>
                    </div>
                  </div>
                </div>
              );
              })}
            </div>
          </div>

          {/* Top IPs */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold mb-3">{t('auditTopIps')}</h3>
            <div className="space-y-2">
              {auditStatsData.top_ips.map((ip, idx) => (
                <div key={idx} className="flex items-center gap-3 p-3 rounded-lg border">
                  <div className="text-sm font-mono flex-shrink-0 w-8">#{idx + 1}</div>
                  <div className="text-sm font-mono flex-1">{ip.ip_address}</div>
                  <div className="text-sm font-medium">{t('auditRequestCount', { count: ip.request_count })}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Event Distribution */}
          <div>
            <h3 className="text-lg font-semibold mb-3">{t('auditEventDistribution')}</h3>
            <div className="space-y-2">
              {auditStatsData.event_distribution.map((event, idx) => (
                <div key={idx} className="flex items-center gap-3">
                  <div className="text-sm w-48 flex-shrink-0">{event.event_type}</div>
                  <div className="flex-1">
                    <div className="h-6 bg-muted rounded-lg overflow-hidden">
                      <div
                        className="h-full bg-primary flex items-center justify-end pr-2 text-xs text-white font-medium"
                        style={{
                          width: `${
                            auditStatsData.total_events > 0
                              ? (event.count / auditStatsData.total_events) * 100
                              : 0
                          }%`,
                        }}
                      >
                        {event.count}
                      </div>
                    </div>
                  </div>
                  <div className="text-sm text-muted-foreground w-16 text-right">
                    {((event.count / auditStatsData.total_events) * 100).toFixed(1)}%
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>,
    locale,
  );
}
