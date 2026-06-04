'use client';

import { useCallback, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Shield, AlertTriangle, Activity, FileText, Download } from 'lucide-react';
import { localizeReactNode } from '@/lib/utils/localeText';
import { AuditLogsTab } from './AuditLogsTab';
import { AuditStatsTab } from './AuditStatsTab';
import { DependenciesTab } from './DependenciesTab';
import { RateLimitTab } from './RateLimitTab';
import { SecuritySetupPanel } from './SecuritySetupPanel';
import { mapAuditLogEvent, mapAuditStatsResponse } from './auditMappers';
import type {
  AuditLogEvent,
  AuditLogStats,
  RateLimitStatus,
  SecurityDashboardData,
  SecuritySetupHints,
  SecurityTabType,
} from './types';

export default function SecurityDashboard() {
  const locale = useLocale();
  const t = useTranslations('securityDashboard');
  const [activeTab, setActiveTab] = useState<SecurityTabType>('dependencies');
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
        setSetupHints(await response.json());
      }
    } catch (err) {
      console.error('Failed to fetch security setup hints:', err);
    }
  }, []);

  const fetchSecurityData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/security/dashboard');
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      setData(await response.json());
      setError(null);
    } catch (err) {
      console.error('Failed to fetch security data:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchRateLimitData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/security/rate-limits');
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
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
  }, []);

  const fetchAuditLogData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/security/audit/logs?limit=100');
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      const result = await response.json();
      const rawEvents = Array.isArray(result.events) ? result.events : [];
      setAuditLogData(rawEvents.map((log: Record<string, unknown>) => mapAuditLogEvent(log)));
      setAuditLive(Boolean(result.isLive));
      setError(null);
    } catch (err) {
      console.error('Failed to fetch audit log data:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAuditStatsData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/security/audit/stats?hours=24');
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      const result = await response.json();
      setAuditStatsData(mapAuditStatsResponse(result as Record<string, unknown>));
      setAuditLive(Boolean(result.isLive));
      setError(null);
    } catch (err) {
      console.error('Failed to fetch audit stats data:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSetupHints();
  }, [fetchSetupHints]);

  useEffect(() => {
    if (activeTab === 'dependencies') fetchSecurityData();
    else if (activeTab === 'rate-limit') fetchRateLimitData();
    else if (activeTab === 'audit-logs') fetchAuditLogData();
    else if (activeTab === 'audit-stats') fetchAuditStatsData();
  }, [activeTab, fetchSecurityData, fetchRateLimitData, fetchAuditLogData, fetchAuditStatsData]);

  useEffect(() => {
    if (auditLogData.length === 0) {
      setFilteredAuditLogData([]);
      return;
    }
    let filtered = auditLogData;
    if (searchUserId) {
      filtered = filtered.filter((event) =>
        event.user_id?.toLowerCase().includes(searchUserId.toLowerCase()),
      );
    }
    if (searchEventType) {
      filtered = filtered.filter((event) =>
        event.event_type.toLowerCase().includes(searchEventType.toLowerCase()),
      );
    }
    if (searchResult !== 'all') {
      filtered =
        searchResult === 'success'
          ? filtered.filter((event) => event.result === 'success')
          : filtered.filter((event) => event.result !== 'success');
    }
    setFilteredAuditLogData(filtered);
  }, [auditLogData, searchUserId, searchEventType, searchResult]);

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

  const exportAuditLogs = async (format: 'csv' | 'json') => {
    try {
      const response = await fetch(`/api/v1/security/audit/export?format=${format}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
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

  const refreshActiveTab = () => {
    if (activeTab === 'dependencies') fetchSecurityData();
    else if (activeTab === 'rate-limit') fetchRateLimitData();
    else if (activeTab === 'audit-logs') fetchAuditLogData();
    else if (activeTab === 'audit-stats') fetchAuditStatsData();
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
            <button onClick={refreshActiveTab} className="mt-2 text-sm text-primary hover:underline">
              {t('retry')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (activeTab === 'dependencies' && !data) return null;

  const tabs = [
    { id: 'dependencies' as SecurityTabType, label: t('tabDependencies'), icon: Shield },
    { id: 'rate-limit' as SecurityTabType, label: t('tabRateLimit'), icon: Activity },
    { id: 'audit-logs' as SecurityTabType, label: t('tabAuditLogs'), icon: FileText },
    { id: 'audit-stats' as SecurityTabType, label: t('tabAuditStats'), icon: Activity },
  ];

  return localizeReactNode(
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Shield className="w-8 h-8" />
            {t('title')}
          </h1>
          <p className="text-muted-foreground mt-1">{t('subtitle')}</p>
          {data?.dataSource && (
            <p className="text-xs text-muted-foreground mt-2">{dataSourceLabel(data.dataSource)}</p>
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
            onClick={refreshActiveTab}
            className="px-4 py-2 rounded-lg border hover:bg-accent transition-colors"
          >
            {t('refresh')}
          </button>
        </div>
      </div>

      {setupHints && (
        <SecuritySetupPanel
          setupHints={setupHints}
          urlCopied={urlCopied}
          onCopyWebhookUrl={copyWebhookUrl}
        />
      )}

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

      {activeTab === 'dependencies' && data && (
        <DependenciesTab data={data} githubTokenConfigured={setupHints?.githubTokenConfigured} />
      )}
      {activeTab === 'rate-limit' && (
        <RateLimitTab rateLimitData={rateLimitData} rateLimitLive={rateLimitLive} />
      )}
      {activeTab === 'audit-logs' && (
        <AuditLogsTab
          auditLive={auditLive}
          auditLogData={auditLogData}
          filteredAuditLogData={filteredAuditLogData}
          searchUserId={searchUserId}
          searchEventType={searchEventType}
          searchResult={searchResult}
          onSearchUserIdChange={setSearchUserId}
          onSearchEventTypeChange={setSearchEventType}
          onSearchResultChange={setSearchResult}
        />
      )}
      {activeTab === 'audit-stats' && auditStatsData && (
        <AuditStatsTab auditStatsData={auditStatsData} auditLive={auditLive} />
      )}
    </div>,
    locale,
  );
}
