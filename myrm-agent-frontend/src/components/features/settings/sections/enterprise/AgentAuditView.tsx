'use client';

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { IconActivity, IconAlertTriangle, IconBot } from '@/components/features/icons/PremiumIcons';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { type OrgAgentAuditResponse, queryOrgAgentAudit } from '@/services/enterprise-admin';
import { getMyOrg } from '@/services/enterprise-org';
import SettingsSection from '../SettingsSection';
import { AgentEventRow, eventKey } from './AgentEventRow';

const AgentAuditView = memo(() => {
  const t = useTranslations('settings.enterprise.audit');
  const [orgId, setOrgId] = useState('');
  const [data, setData] = useState<OrgAgentAuditResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hours, setHours] = useState<number>(24);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const requestSeqRef = useRef(0);

  const loadData = useCallback(
    async (targetOrgId: string, targetHours: number) => {
      const seq = ++requestSeqRef.current;
      try {
        setLoading(true);
        const result = await queryOrgAgentAudit(targetOrgId, { hours: targetHours, limit: 200 });
        if (seq !== requestSeqRef.current) {return;}
        setData(result);
        setError(null);
      } catch (e) {
        if (seq !== requestSeqRef.current) {return;}
        setError(e instanceof Error ? e.message : 'Failed to load agent activity');
        toast.error(e instanceof Error ? e.message : 'Failed to load agent activity');
      } finally {
        if (seq === requestSeqRef.current) {setLoading(false);}
      }
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const org = await getMyOrg();
        if (cancelled) {return;}
        setOrgId(org.id);
        await loadData(org.id, 24);
      } catch {
        if (cancelled) {return;}
        setError('Failed to load organization');
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      requestSeqRef.current += 1;
    };
  }, [loadData]);

  const onHoursChange = useCallback(
    (value: string) => {
      const next = Number(value);
      setHours(next);
      if (orgId) {
        void loadData(orgId, next);
      }
    },
    [orgId, loadData],
  );

  const toggleExpanded = useCallback((key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {next.delete(key);} else {next.add(key);}
      return next;
    });
  }, []);

  const events = useMemo(() => data?.events ?? [], [data]);
  const securityEvents = useMemo(() => events.filter((e) => e.type === 'security_audit'), [events]);
  const toolEvents = useMemo(
    () => events.filter((e) => e.type === 'tool_call_start' || e.type === 'tool_call_finish'),
    [events],
  );

  if (loading && !data) {
    return (
      <SettingsSection title={t('agentTitle')} description={t('agentDescription')}>
        <div className="animate-pulse space-y-4">
          <div className="h-48 bg-muted rounded" />
          <div className="h-32 bg-muted rounded" />
        </div>
      </SettingsSection>
    );
  }

  return (
    <div className="space-y-6">
      <SettingsSection
        title={
          <span className="flex items-center gap-2">
            <IconBot className="h-5 w-5" />
            {t('agentTitle')}
          </span>
        }
        description={t('agentDescription')}
        action={
          <div className="flex items-center gap-2">
            <Select value={String(hours)} onValueChange={onHoursChange}>
              <SelectTrigger className="w-24 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="24">24h</SelectItem>
                <SelectItem value="168">7d</SelectItem>
                <SelectItem value="720">30d</SelectItem>
              </SelectContent>
            </Select>
          </div>
        }
      >
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-700 dark:text-red-400">
            <IconAlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">{t('agentLoadFailed')}</p>
              <p className="mt-0.5 break-all">{error}</p>
            </div>
          </div>
        )}
        {data && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="rounded-lg border p-3 text-center">
                <div className="text-2xl font-bold">{data.total}</div>
                <div className="text-xs text-muted-foreground">{t('agentTotalEvents')}</div>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <div className="text-2xl font-bold">{toolEvents.length}</div>
                <div className="text-xs text-muted-foreground">{t('agentToolCalls')}</div>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <div className="text-2xl font-bold text-red-600">{securityEvents.length}</div>
                <div className="text-xs text-muted-foreground">{t('agentSecurityEvents')}</div>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <div className="text-2xl font-bold">{data.scanned_sandboxes}</div>
                <div className="text-xs text-muted-foreground">{t('agentScannedSandboxes')}</div>
              </div>
            </div>

            {data.failed_sandboxes.length > 0 && (
              <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-400">
                <IconAlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium">{t('agentFailedSandboxes')}</p>
                  <p className="mt-0.5 font-mono text-amber-600/80 dark:text-amber-400/80 break-all">
                    {data.failed_sandboxes.join(', ')}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </SettingsSection>

      <SettingsSection
        title={
          <span className="flex items-center gap-2">
            <IconActivity className="h-4 w-4" />
            {t('agentEventList')}
          </span>
        }
      >
        <div className="space-y-1.5 max-h-[26rem] overflow-y-auto pr-1">
          {data && data.total > events.length && (
            <p className="pb-1 px-0.5 text-[10px] text-muted-foreground">
              {t('agentShowingLatest', { shown: events.length, total: data.total })}
            </p>
          )}
          {events.map((event) => (
            <AgentEventRow
              key={eventKey(event)}
              event={event}
              expanded={expanded.has(eventKey(event))}
              onToggle={() => toggleExpanded(eventKey(event))}
            />
          ))}
          {events.length === 0 && (
            <div className="text-center py-8 text-muted-foreground text-sm">{t('agentNoEvents')}</div>
          )}
        </div>
      </SettingsSection>
    </div>
  );
});
AgentAuditView.displayName = 'AgentAuditView';

export default AgentAuditView;
