/**
 * [INPUT] skills growth API via @/services, SkillGrowthCaseCard (POS: 技能进化提案卡片)
 * [OUTPUT] PendingEvolutionsDashboard: 待审核技能进化列表（Simple/Detailed 双视图，localStorage 持久化）
 * [POS] features/skills 技能进化审核入口面板
 */
'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, CheckCircle2, Clock3, List, RefreshCw, ShieldAlert, SquareStack } from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Skeleton } from '@/components/primitives/skeleton';
import SkillGrowthCaseCard, { type SkillGrowthViewMode } from '@/components/features/skills/SkillGrowthCaseCard';
import SettingsSection from '@/components/features/settings/sections/SettingsSection';
import { toast } from '@/hooks/useToast';
import {
  approveSkillGrowthCase,
  getSkillGrowthSummary,
  listSkillGrowthCases,
  rejectSkillGrowthCase,
  reviseSkillGrowthCase,
  type SkillGrowthCaseSummary,
  type SkillGrowthSummary,
} from '@/services/skill-growth';
import { createCronJob } from '@/services/cron';
import { useSkillStore } from '@/store/skill';
import useAuthStore from '@/store/useAuthStore';
import { cn } from '@/lib/utils/classnameUtils';

type GrowthFilter = 'all' | 'pending' | 'applied' | 'blocked' | 'reviewed';

const FILTER_ORDER: GrowthFilter[] = ['all', 'pending', 'applied', 'blocked', 'reviewed'];
const VIEW_MODE_KEY = 'myrm:skill-growth-view-mode';
const LIST_CASES_LIMIT = 100;

const EMPTY_SUMMARY: SkillGrowthSummary = {
  total: 0,
  pendingReview: 0,
  autoApplied: 0,
  blocked: 0,
};

function matchesFilter(item: SkillGrowthCaseSummary, filter: GrowthFilter): boolean {
  if (filter === 'all') return true;
  if (filter === 'pending') return item.status === 'PENDING_REVIEW' || item.status === 'APPLY_FAILED';
  if (filter === 'applied') return item.status === 'AUTO_APPLIED';
  if (filter === 'blocked') return item.status === 'BLOCKED_LOCKED' || item.status === 'FAILED_SCAN';
  return item.status === 'APPROVED' || item.status === 'REJECTED';
}

interface SummaryCardProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  toneClassName: string;
}

function SummaryCard({ icon: Icon, label, value, toneClassName }: SummaryCardProps) {
  return (
    <div className="rounded-2xl border bg-background p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="text-2xl font-semibold text-foreground">{value}</p>
        </div>
        <div className={cn('rounded-2xl border p-2.5', toneClassName)}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </div>
  );
}

export function PendingEvolutionsDashboard() {
  const t = useTranslations('settings.skills.growth');
  const { user } = useAuthStore();
  const { fetchLocalSkills, fetchUserSkillConfig } = useSkillStore();

  const [cases, setCases] = useState<SkillGrowthCaseSummary[]>([]);
  const [listTotal, setListTotal] = useState(0);
  const [summary, setSummary] = useState<SkillGrowthSummary>(EMPTY_SUMMARY);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [processingCaseId, setProcessingCaseId] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<GrowthFilter>('all');
  const [viewMode, setViewMode] = useState<SkillGrowthViewMode>(() => {
    if (typeof window === 'undefined') return 'simple';
    return (localStorage.getItem(VIEW_MODE_KEY) as SkillGrowthViewMode) || 'simple';
  });

  const toggleViewMode = useCallback(() => {
    setViewMode((prev) => {
      const next: SkillGrowthViewMode = prev === 'simple' ? 'detailed' : 'simple';
      localStorage.setItem(VIEW_MODE_KEY, next);
      return next;
    });
  }, []);

  const refreshSkillInventory = useCallback(async () => {
    await Promise.all([fetchUserSkillConfig(true), fetchLocalSkills()]);
  }, [fetchLocalSkills, fetchUserSkillConfig]);

  const loadCases = useCallback(
    async (silent: boolean = false) => {
      if (!user?.id) {
        setCases([]);
        setListTotal(0);
        setSummary(EMPTY_SUMMARY);
        setError(null);
        setIsLoading(false);
        return;
      }

      if (!silent) {
        setIsLoading(true);
      }
      setError(null);

      try {
        const [casesResult, summaryResult] = await Promise.allSettled([
          listSkillGrowthCases(LIST_CASES_LIMIT),
          getSkillGrowthSummary(),
        ]);

        if (casesResult.status === 'rejected') {
          throw casesResult.reason;
        }

        const latestList = casesResult.value;
        setCases(latestList.items);
        setListTotal(latestList.total);

        if (summaryResult.status === 'fulfilled') {
          setSummary(summaryResult.value);
        } else {
          setSummary({
            total: latestList.items.length,
            pendingReview: latestList.items.filter(
              (item) => item.status === 'PENDING_REVIEW' || item.status === 'APPLY_FAILED',
            ).length,
            autoApplied: latestList.items.filter((item) => item.status === 'AUTO_APPLIED').length,
            blocked: latestList.items.filter(
              (item) => item.status === 'BLOCKED_LOCKED' || item.status === 'FAILED_SCAN',
            ).length,
          });
        }
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : t('loadFailed'));
      } finally {
        setIsLoading(false);
      }
    },
    [t, user?.id],
  );

  useEffect(() => {
    void loadCases();
  }, [loadCases]);

  useEffect(() => {
    const handleRefresh = () => {
      void loadCases(true);
      void refreshSkillInventory();
    };

    window.addEventListener('skill-growth-updated', handleRefresh);
    window.addEventListener('skill-evolved', handleRefresh);
    return () => {
      window.removeEventListener('skill-growth-updated', handleRefresh);
      window.removeEventListener('skill-evolved', handleRefresh);
    };
  }, [loadCases, refreshSkillInventory]);

  const showListScopeHint = listTotal > cases.length;

  const filterCounts = useMemo((): Record<GrowthFilter, number> => {
    const reviewed = Math.max(
      0,
      summary.total - summary.pendingReview - summary.autoApplied - summary.blocked,
    );
    return {
      all: listTotal,
      pending: summary.pendingReview,
      applied: summary.autoApplied,
      blocked: summary.blocked,
      reviewed,
    };
  }, [listTotal, summary]);

  const filteredCases = useMemo(() => {
    return cases.filter((item) => matchesFilter(item, activeFilter));
  }, [activeFilter, cases]);

  const handleApprove = useCallback(
    async (item: SkillGrowthCaseSummary, applyMode: 'immediate' | 'shadow' = 'immediate') => {
      if (!user?.id || processingCaseId) return;
      setProcessingCaseId(item.id);
      try {
        const result = await approveSkillGrowthCase(item, applyMode);
        const nextStatus = result.apply_status === 'FAILED' ? 'APPLY_FAILED' : 'APPROVED';
        if (result.apply_status === 'FAILED') {
          toast.error(result.apply_error ?? result.remediation ?? t('approveFailed', { name: item.skillName }));
        } else {
          toast.success(
            applyMode === 'shadow'
              ? t('approveShadowSuccess', { name: item.skillName })
              : t('approveSuccess', { name: item.skillName }),
          );
        }
        window.dispatchEvent(
          new CustomEvent('skill-growth-updated', {
            detail: { caseId: item.id, status: nextStatus, source: item.source },
          }),
        );
        await Promise.all([loadCases(true), refreshSkillInventory()]);
      } catch (approveError) {
        toast.error(
          approveError instanceof Error ? approveError.message : t('approveFailed', { name: item.skillName }),
        );
      } finally {
        setProcessingCaseId(null);
      }
    },
    [loadCases, processingCaseId, refreshSkillInventory, t, user?.id],
  );

  const handleReject = useCallback(
    async (item: SkillGrowthCaseSummary, reason?: string) => {
      if (!user?.id || processingCaseId) return;
      setProcessingCaseId(item.id);
      try {
        await rejectSkillGrowthCase(item, reason);
        toast.success(t('rejectSuccess', { name: item.skillName }));
        window.dispatchEvent(
          new CustomEvent('skill-growth-updated', {
            detail: { caseId: item.id, status: 'REJECTED', source: item.source },
          }),
        );
        await loadCases(true);
      } catch (rejectError) {
        toast.error(rejectError instanceof Error ? rejectError.message : t('rejectFailed', { name: item.skillName }));
      } finally {
        setProcessingCaseId(null);
      }
    },
    [loadCases, processingCaseId, t, user?.id],
  );

  const handleRevise = useCallback(
    async (item: SkillGrowthCaseSummary, evolvedContent: string) => {
      if (!user?.id || processingCaseId) return;
      setProcessingCaseId(item.id);
      try {
        const result = await reviseSkillGrowthCase(item, evolvedContent);
        if (result.test_passed) {
          toast.success(t('reviseSuccess', { name: item.skillName }));
        } else {
          toast.error(t('reviseFailedScan', { name: item.skillName }));
        }
        await loadCases(true);
      } catch (reviseError) {
        toast.error(reviseError instanceof Error ? reviseError.message : t('reviseFailed', { name: item.skillName }));
      } finally {
        setProcessingCaseId(null);
      }
    },
    [loadCases, processingCaseId, t, user?.id],
  );

  const handleCreateCron = useCallback(
    async (item: SkillGrowthCaseSummary, scheduleHint: string) => {
      if (!user?.id || processingCaseId) return;
      setProcessingCaseId(item.id);
      try {
        await createCronJob({
          name: item.skillName || scheduleHint,
          job_type: 'agent',
          schedule: { type: 'cron', cron: scheduleHint, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone },
          prompt: item.proposedContent || item.description || scheduleHint,
        });
        await approveSkillGrowthCase(item, 'immediate');
        toast.success(t('cronCreated', { name: item.skillName }));
        window.dispatchEvent(
          new CustomEvent('skill-growth-updated', {
            detail: { caseId: item.id, status: 'APPROVED', source: item.source },
          }),
        );
        await loadCases(true);
      } catch (cronError) {
        toast.error(cronError instanceof Error ? cronError.message : t('cronCreateFailed', { name: item.skillName }));
      } finally {
        setProcessingCaseId(null);
      }
    },
    [loadCases, processingCaseId, t, user?.id],
  );

  return (
    <SettingsSection
      title={t('title')}
      description={t('description')}
      action={
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={toggleViewMode}
          >
            {viewMode === 'simple' ? <List className="h-4 w-4" /> : <SquareStack className="h-4 w-4" />}
            {t(`viewMode.${viewMode}` as Parameters<typeof t>[0])}
          </Button>
          <Button variant="outline" size="sm" onClick={() => void loadCases()} disabled={isLoading}>
            <RefreshCw className={cn('mr-2 h-4 w-4', isLoading && 'animate-spin')} />
            {t('refresh')}
          </Button>
        </div>
      }
    >
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          icon={IconGlow}
          label={t('summary.total')}
          value={summary.total}
          toneClassName="border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-300"
        />
        <SummaryCard
          icon={Clock3}
          label={t('summary.pendingReview')}
          value={summary.pendingReview}
          toneClassName="border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300"
        />
        <SummaryCard
          icon={CheckCircle2}
          label={t('summary.autoApplied')}
          value={summary.autoApplied}
          toneClassName="border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300"
        />
        <SummaryCard
          icon={ShieldAlert}
          label={t('summary.blocked')}
          value={summary.blocked}
          toneClassName="border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300"
        />
      </div>

      {showListScopeHint && (
        <p className="text-sm text-muted-foreground">
          {t('listScopeHint', { shown: cases.length, total: listTotal })}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {FILTER_ORDER.map((filter) => {
          const isActive = filter === activeFilter;
          const count = filterCounts[filter];
          return (
            <Button
              key={filter}
              variant={isActive ? 'default' : 'outline'}
              size="sm"
              className="gap-2 rounded-full"
              onClick={() => setActiveFilter(filter)}
            >
              <span>{t(`filters.${filter}` as Parameters<typeof t>[0])}</span>
              <Badge variant={isActive ? 'secondary' : 'outline'} className="px-1.5 py-0 text-[11px]">
                {count}
              </Badge>
            </Button>
          );
        })}
      </div>

      {!user?.id && (
        <div className="rounded-2xl border border-dashed p-8 text-center text-sm text-muted-foreground">
          {t('authRequired')}
        </div>
      )}

      {user?.id && isLoading && (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="rounded-2xl border bg-background p-4">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="mt-3 h-4 w-full" />
              <Skeleton className="mt-2 h-28 w-full" />
            </div>
          ))}
        </div>
      )}

      {user?.id && !isLoading && error && (
        <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-6 text-sm text-destructive">
          {error}
        </div>
      )}

      {user?.id && !isLoading && !error && filteredCases.length === 0 && (
        <div className="rounded-2xl border border-dashed p-10 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-muted">
            <AlertTriangle className="h-5 w-5 text-muted-foreground" />
          </div>
          <p className="mt-4 text-base font-medium text-foreground">{t('empty.title')}</p>
          <p className="mt-2 text-sm text-muted-foreground">{t('empty.description')}</p>
        </div>
      )}

      {user?.id && !isLoading && !error && filteredCases.length > 0 && (
        <div className="space-y-4">
          {filteredCases.map((item) => (
            <SkillGrowthCaseCard
              key={item.id}
              item={item}
              isProcessing={processingCaseId === item.id}
              viewMode={viewMode}
              onApprove={() => handleApprove(item, 'immediate')}
              onApproveShadow={() => handleApprove(item, 'shadow')}
              onReject={(reason?: string) => handleReject(item, reason)}
              onRevise={(evolvedContent: string) => handleRevise(item, evolvedContent)}
              onCreateCron={
                item.growthType === 'cron_suggestion' && item.formMetadata?.scheduleHint
                  ? (hint: string) => handleCreateCron(item, hint)
                  : undefined
              }
            />
          ))}
        </div>
      )}
    </SettingsSection>
  );
}
