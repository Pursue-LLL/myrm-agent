'use client';

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Download, Filter, ShieldAlert } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import SettingsSection from '../SettingsSection';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Badge } from '@/components/primitives/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives/select';
import {
  type AuditEvent,
  type AuditStatsResponse,
  type AuditLogFilters,
  getAuditStats,
  queryAuditLogs,
  exportAuditLogs,
} from '@/services/enterprise-admin';

const PIE_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16'];

const SEVERITY_COLORS: Record<string, string> = {
  info: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  warning: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
};

const EnterpriseAuditTab = memo(() => {
  const t = useTranslations('settings.enterprise.audit');
  const [stats, setStats] = useState<AuditStatsResponse | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [hours, setHours] = useState<number>(24);
  const [filters, setFilters] = useState<AuditLogFilters>({ limit: 50 });

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [statsData, logsData] = await Promise.all([
        getAuditStats(hours),
        queryAuditLogs(filters),
      ]);
      setStats(statsData);
      setEvents(logsData.events);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to load audit data');
    } finally {
      setLoading(false);
    }
  }, [hours, filters]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleExport = useCallback(async (format: 'csv' | 'json') => {
    try {
      const blob = await exportAuditLogs(format, filters);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_logs.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(t('exportSuccess'));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Export failed');
    }
  }, [filters, t]);

  const handleFilterChange = useCallback((key: keyof AuditLogFilters, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value || undefined }));
  }, []);

  const successRate = useMemo(() => {
    if (!stats || stats.total_events === 0) return 0;
    return Math.round((stats.success_vs_failed.success / stats.total_events) * 100);
  }, [stats]);

  if (loading && !stats) {
    return (
      <SettingsSection title={t('title')} description={t('description')}>
        <div className="animate-pulse space-y-4">
          <div className="h-48 bg-muted rounded" />
          <div className="h-32 bg-muted rounded" />
        </div>
      </SettingsSection>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats Overview */}
      <SettingsSection
        title={
          <span className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5" />
            {t('title')}
          </span>
        }
        description={t('description')}
        action={
          <div className="flex items-center gap-2">
            <Select value={String(hours)} onValueChange={(v) => setHours(Number(v))}>
              <SelectTrigger className="w-24 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="24">24h</SelectItem>
                <SelectItem value="168">7d</SelectItem>
                <SelectItem value="720">30d</SelectItem>
              </SelectContent>
            </Select>
            <Button size="sm" variant="outline" onClick={() => handleExport('csv')}>
              <Download className="h-3.5 w-3.5 mr-1" />
              CSV
            </Button>
            <Button size="sm" variant="outline" onClick={() => handleExport('json')}>
              <Download className="h-3.5 w-3.5 mr-1" />
              JSON
            </Button>
          </div>
        }
      >
        {stats && (
          <div className="space-y-4">
            {/* KPI Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="rounded-lg border p-3 text-center">
                <div className="text-2xl font-bold">{stats.total_events}</div>
                <div className="text-xs text-muted-foreground">{t('totalEvents')}</div>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <div className="text-2xl font-bold text-green-600">{successRate}%</div>
                <div className="text-xs text-muted-foreground">{t('successRate')}</div>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <div className="text-2xl font-bold text-red-600">{stats.success_vs_failed.failed}</div>
                <div className="text-xs text-muted-foreground">{t('failedEvents')}</div>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <div className="text-2xl font-bold">{stats.top_ips.length}</div>
                <div className="text-xs text-muted-foreground">{t('uniqueIps')}</div>
              </div>
            </div>

            {/* Time Series Chart */}
            {stats.time_series.length > 0 && (
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={stats.time_series}>
                    <XAxis dataKey="timestamp" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(11, 16)} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip />
                    <Area type="monotone" dataKey="success" stackId="1" stroke="#10b981" fill="#10b981" fillOpacity={0.3} />
                    <Area type="monotone" dataKey="failed" stackId="1" stroke="#ef4444" fill="#ef4444" fillOpacity={0.3} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Event Distribution */}
            {stats.event_distribution.length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={stats.event_distribution.slice(0, 8)}
                        dataKey="count"
                        nameKey="event_type"
                        cx="50%"
                        cy="50%"
                        outerRadius={60}
                        label={({ event_type, percent }) => `${event_type.replace(/_/g, ' ')} ${(percent * 100).toFixed(0)}%`}
                        labelLine={false}
                      >
                        {stats.event_distribution.slice(0, 8).map((_, i) => (
                          <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                {stats.top_ips.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-xs font-medium text-muted-foreground mb-2">{t('topIps')}</div>
                    {stats.top_ips.slice(0, 5).map((ip) => (
                      <div key={ip.ip_address} className="flex justify-between text-xs py-1 border-b border-border/30">
                        <span className="font-mono">{ip.ip_address}</span>
                        <span className="text-muted-foreground">{ip.request_count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </SettingsSection>

      {/* Event List */}
      <SettingsSection
        title={
          <span className="flex items-center gap-2">
            <Filter className="h-4 w-4" />
            {t('eventList')}
          </span>
        }
      >
        <div className="space-y-3">
          {/* Filters */}
          <div className="flex flex-wrap gap-2">
            <Input
              className="h-8 w-36 text-xs"
              placeholder={t('filterUserId')}
              onChange={(e) => handleFilterChange('user_id', e.target.value)}
            />
            <Input
              className="h-8 w-36 text-xs"
              placeholder={t('filterSandboxId')}
              onChange={(e) => handleFilterChange('sandbox_id', e.target.value)}
            />
            <Input
              className="h-8 w-40 text-xs"
              placeholder={t('filterEventType')}
              onChange={(e) => handleFilterChange('event_type', e.target.value)}
            />
            <Button size="sm" variant="outline" onClick={loadData} className="h-8">
              {t('apply')}
            </Button>
          </div>

          {/* Event Rows */}
          <div className="space-y-1.5 max-h-72 overflow-y-auto">
            {events.map((ev, idx) => (
              <div
                key={`${ev.timestamp}-${idx}`}
                className="flex items-center justify-between py-1.5 px-3 rounded-lg bg-background/50 border border-border/30 text-xs"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <Badge className={`text-[10px] ${SEVERITY_COLORS[ev.severity] ?? SEVERITY_COLORS.info}`}>
                    {ev.severity}
                  </Badge>
                  <span className="font-mono truncate max-w-32">{ev.event_type.replace(/_/g, ' ')}</span>
                  {ev.user_id && <span className="text-muted-foreground truncate max-w-24">{ev.user_id}</span>}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge variant={ev.result === 'success' ? 'default' : 'destructive'} className="text-[10px]">
                    {ev.result}
                  </Badge>
                  <span className="text-muted-foreground">{new Date(ev.timestamp).toLocaleString()}</span>
                </div>
              </div>
            ))}
            {events.length === 0 && (
              <div className="text-center py-8 text-muted-foreground text-sm">{t('noEvents')}</div>
            )}
          </div>
        </div>
      </SettingsSection>
    </div>
  );
});

EnterpriseAuditTab.displayName = 'EnterpriseAuditTab';

export default EnterpriseAuditTab;
