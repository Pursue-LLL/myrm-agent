'use client';

import { useTranslations } from 'next-intl';
import { Activity } from 'lucide-react';
import type { AuditLogStats } from './types';

interface AuditStatsTabProps {
  auditStatsData: AuditLogStats;
  auditLive: boolean;
}

export function AuditStatsTab({ auditStatsData, auditLive }: AuditStatsTabProps) {
  const t = useTranslations('securityDashboard');

  return (
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
                {auditStatsData.total_events > 0
                  ? `${((event.count / auditStatsData.total_events) * 100).toFixed(1)}%`
                  : '0%'}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
