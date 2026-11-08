'use client';

/**
 * [INPUT] @/services/memory/commandCenter (POS: 诊断运行、探针与修复计划类型), ./MemoryDoctorTrend::CategoryBreakdown (POS: 类别通过率)
 * [OUTPUT] DiagnosticRunSummary: 最近一次诊断运行的摘要、benchmark 指标与探针结果；RepairPlanList: probe 级修复计划；ProbeDetails: 检查项的探针详情
 * [POS] Memory Doctor 面板的单次诊断运行视图，可执行的修复动作经 onDoctorAction 交回面板。
 */

import type {
  MemoryCommandBenchmarkSummary,
  MemoryCommandDiagnosticProbeResult,
  MemoryCommandDiagnosticRun,
  MemoryCommandRepairPlan,
} from '@/services/memory/commandCenter';
import {
  type DoctorExecutableAction,
  type MemoryTranslation,
  formatDuration,
  formatPercent,
  formatTime,
  isDoctorCheckId,
  isDoctorRepairAction,
  isExecutableDoctorAction,
} from './memoryDoctorModel';
import { StatusPill } from './MemoryDoctorStatusPill';
import { CategoryBreakdown } from './MemoryDoctorTrend';

export const DiagnosticRunSummary = ({
  run,
  t,
  actionId,
  onDoctorAction,
}: {
  run: MemoryCommandDiagnosticRun;
  t: MemoryTranslation;
  actionId: string | null;
  onDoctorAction: (action: DoctorExecutableAction) => void;
}) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="text-sm font-medium text-foreground">{t('commandCenter.doctorLastRun')}</div>
        <div className="mt-1 text-[11px] text-muted-foreground">{formatTime(run.completed_at)}</div>
      </div>
      <StatusPill status={run.status} t={t} />
    </div>
    <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-muted-foreground md:grid-cols-4">
      <FactInline label={t('commandCenter.doctorProbeCount')} value={String(run.probe_count)} />
      <FactInline label={t('commandCenter.doctorFailedCount')} value={String(run.failed_count)} />
      <FactInline label={t('commandCenter.doctorRunDuration')} value={formatDuration(run.duration_ms)} />
      <FactInline label={t('commandCenter.doctorRunId')} value={run.id} />
    </div>
    <div className="mt-3 grid gap-2 text-[11px] text-muted-foreground md:grid-cols-2">
      <FactInline label={t('commandCenter.doctorRunSummary')} value={run.summary} />
      <FactInline
        label={t('commandCenter.doctorAuditStatus')}
        value={
          run.audit_recorded
            ? t('commandCenter.doctorAuditRecorded')
            : run.audit_error || t('commandCenter.doctorAuditMissing')
        }
      />
    </div>
    {run.slo && (
      <div className="mt-3 rounded-full border border-border/40 bg-background/70 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-medium text-foreground">{t('commandCenter.doctorSloTitle')}</span>
          <StatusPill status={run.slo.status} t={t} />
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-muted-foreground md:grid-cols-4">
          <FactInline label={t('commandCenter.doctorSloWindow')} value={String(run.slo.window_runs)} />
          <FactInline label={t('commandCenter.doctorSloPassRate')} value={formatPercent(run.slo.pass_rate)} />
          <FactInline label={t('commandCenter.doctorSloFailedRuns')} value={String(run.slo.failed_runs)} />
          <FactInline
            label={t('commandCenter.doctorSloAvgDuration')}
            value={formatDuration(run.slo.average_duration_ms)}
          />
        </div>
      </div>
    )}
    <div className="mt-3 grid gap-2 md:grid-cols-2">
      {run.probes.map((probe) => (
        <DiagnosticProbeRow key={probe.id} probe={probe} t={t} actionId={actionId} onDoctorAction={onDoctorAction} />
      ))}
    </div>
  </div>
);

const DiagnosticProbeRow = ({
  probe,
  t,
  actionId,
  onDoctorAction,
}: {
  probe: MemoryCommandDiagnosticProbeResult;
  t: MemoryTranslation;
  actionId: string | null;
  onDoctorAction: (action: DoctorExecutableAction) => void;
}) => (
  <div className="rounded-full border border-border/40 bg-background/70 px-3 py-2">
    <div className="flex items-start justify-between gap-2">
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-foreground">
          {isDoctorCheckId(probe.id) ? t(`commandCenter.doctorCheck.${probe.id}.label`) : probe.label}
        </div>
        {!probe.benchmark_summary && (
          <div className="mt-1 line-clamp-4 text-[11px] leading-5 text-muted-foreground">{probe.evidence}</div>
        )}
      </div>
      <StatusPill status={probe.status} t={t} />
    </div>
    {probe.benchmark_summary && <BenchmarkMetrics summary={probe.benchmark_summary} t={t} />}
    <div className="mt-2 text-[11px] text-muted-foreground">
      {t('commandCenter.doctorProbeDuration', { duration: formatDuration(probe.duration_ms) })}
    </div>
    <ProbeDetails
      impact={probe.impact}
      nextAction={probe.next_action}
      canAutoFix={probe.can_auto_fix}
      safeToRetry={probe.safe_to_retry}
      t={t}
    />
    <RepairPlanList plans={probe.repair_plans} t={t} actionId={actionId} onDoctorAction={onDoctorAction} />
  </div>
);

const MetricCard = ({ label, value, colorClass }: { label: string; value: string; colorClass?: string }) => (
  <div className="rounded-full border border-border/30 bg-muted/30 px-2 py-1.5">
    <div className="text-[10px] text-muted-foreground">{label}</div>
    <div className={`text-xs font-semibold ${colorClass ?? 'text-foreground'}`}>{value}</div>
  </div>
);

const metricColor = (value: number, thresholds: { good: number; warn: number }): string => {
  if (value >= thresholds.good) {
    return 'text-emerald-500 dark:text-emerald-400';
  }
  if (value >= thresholds.warn) {
    return 'text-amber-500 dark:text-amber-400';
  }
  return 'text-red-500 dark:text-red-400';
};

const BenchmarkMetrics = ({ summary, t }: { summary: MemoryCommandBenchmarkSummary; t: MemoryTranslation }) => {
  const k = String(summary.top_k);

  return (
    <div className="mt-2 space-y-2">
      <div className="grid grid-cols-2 gap-1.5 md:grid-cols-4">
        <MetricCard
          label={t('commandCenter.benchmarkCases')}
          value={`${summary.passed_count}/${summary.case_count}`}
          colorClass={metricColor(summary.passed_count / Math.max(summary.case_count, 1), { good: 1, warn: 0.8 })}
        />
        <MetricCard
          label={t('commandCenter.benchmarkRecall', { k })}
          value={formatPercent(summary.recall_at_k)}
          colorClass={metricColor(summary.recall_at_k, { good: 0.95, warn: 0.8 })}
        />
        <MetricCard
          label={t('commandCenter.benchmarkNdcg', { k })}
          value={formatPercent(summary.ndcg_at_k)}
          colorClass={metricColor(summary.ndcg_at_k, { good: 0.9, warn: 0.7 })}
        />
        <MetricCard
          label={t('commandCenter.benchmarkMrr')}
          value={formatPercent(summary.mrr_score)}
          colorClass={metricColor(summary.mrr_score, { good: 0.9, warn: 0.7 })}
        />
        <MetricCard
          label={t('commandCenter.benchmarkPrecision', { k })}
          value={formatPercent(summary.precision_at_k)}
        />
        {summary.duplicate_rate !== undefined && (
          <MetricCard
            label={t('commandCenter.benchmarkDuplicateRate')}
            value={formatPercent(summary.duplicate_rate)}
            colorClass={metricColor(1 - summary.duplicate_rate, { good: 0.8, warn: 0.6 })}
          />
        )}
        {summary.distinct_source_ratio !== undefined && (
          <MetricCard
            label={t('commandCenter.benchmarkDistinctSources')}
            value={formatPercent(summary.distinct_source_ratio)}
            colorClass={metricColor(summary.distinct_source_ratio, { good: 0.8, warn: 0.6 })}
          />
        )}
        <MetricCard label={t('commandCenter.benchmarkLatencyP50')} value={`${Math.round(summary.latency_p50_ms)}ms`} />
        <MetricCard label={t('commandCenter.benchmarkLatencyP95')} value={`${Math.round(summary.latency_p95_ms)}ms`} />
        <MetricCard label={t('commandCenter.benchmarkLatencyP99')} value={`${Math.round(summary.latency_p99_ms)}ms`} />
      </div>
      <CategoryBreakdown categories={summary.categories} t={t} bordered={false} />
    </div>
  );
};

export const RepairPlanList = ({
  plans,
  t,
  actionId,
  onDoctorAction,
}: {
  plans: MemoryCommandRepairPlan[];
  t: MemoryTranslation;
  actionId: string | null;
  onDoctorAction: (action: DoctorExecutableAction) => void;
}) => {
  if (!plans.length) {
    return null;
  }
  return (
    <div className="mt-3 grid gap-2 border-t border-border/40 pt-2">
      {plans.map((plan) => {
        const executableAction = isExecutableDoctorAction(plan.id) ? plan.id : null;
        return (
          <div key={plan.id} className="rounded-full border border-border/40 bg-background/70 px-2 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[11px] font-medium text-foreground">
                {isDoctorRepairAction(plan.id) ? t(`commandCenter.doctorRepairAction.${plan.id}`) : plan.label}
              </span>
              <span className="rounded-full border border-border bg-background px-2 py-0.5 text-[10px] text-muted-foreground">
                {t(`commandCenter.doctorRepairRisk.${plan.risk_level}`)}
              </span>
            </div>
            <div className="mt-2 grid gap-1 text-[11px] leading-5 text-muted-foreground">
              <FactInline label={t('commandCenter.doctorRepairDryRun')} value={formatRepairPlanDryRun(plan, t)} />
              <FactInline
                label={t('commandCenter.doctorRepairExpectedEffect')}
                value={formatRepairPlanExpectedEffect(plan, t)}
              />
            </div>
            {plan.executable && executableAction && (
              <button
                type="button"
                disabled={actionId === `diagnostics:${executableAction}`}
                onClick={() => onDoctorAction(executableAction)}
                className="mt-2 rounded-full border border-border bg-background px-2 py-1 text-[11px] transition-colors hover:bg-accent disabled:opacity-60"
              >
                {t('commandCenter.doctorRepairExecute')}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
};

const formatRepairPlanDryRun = (plan: MemoryCommandRepairPlan, t: MemoryTranslation): string =>
  isDoctorRepairAction(plan.id) ? t(`commandCenter.doctorRepairPlan.${plan.id}.dryRun`) : plan.dry_run_result;

const formatRepairPlanExpectedEffect = (plan: MemoryCommandRepairPlan, t: MemoryTranslation): string =>
  isDoctorRepairAction(plan.id) ? t(`commandCenter.doctorRepairPlan.${plan.id}.expectedEffect`) : plan.expected_effect;

export const ProbeDetails = ({
  impact,
  nextAction,
  canAutoFix,
  safeToRetry,
  t,
}: {
  impact: string;
  nextAction: string;
  canAutoFix: boolean;
  safeToRetry: boolean;
  t: MemoryTranslation;
}) => (
  <div className="mt-3 grid gap-2 border-t border-border/40 pt-2 text-[11px] leading-5 text-muted-foreground">
    {impact && <FactInline label={t('commandCenter.doctorImpact')} value={impact} />}
    {nextAction && <FactInline label={t('commandCenter.doctorNextAction')} value={nextAction} />}
    <div className="flex flex-wrap gap-1.5">
      <span className="rounded-full border border-border bg-background px-2 py-0.5">
        {canAutoFix ? t('commandCenter.doctorAutoFixAvailable') : t('commandCenter.doctorManualFix')}
      </span>
      <span className="rounded-full border border-border bg-background px-2 py-0.5">
        {safeToRetry ? t('commandCenter.doctorSafeToRetry') : t('commandCenter.doctorDoNotRetry')}
      </span>
    </div>
  </div>
);

const FactInline = ({ label, value }: { label: string; value: string }) => (
  <div className="min-w-0">
    <span className="block truncate">{label}</span>
    <span className="block break-words font-medium text-foreground">{value}</span>
  </div>
);
