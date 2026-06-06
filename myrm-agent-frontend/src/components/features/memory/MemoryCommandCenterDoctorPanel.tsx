'use client';

/**
 * [INPUT]
 * @/services/memoryCommandCenter::MemoryCommandCenterResponse (POS: Frontend Personal Brain Command Center client)
 *
 * [OUTPUT]
 * MemoryDoctorPanel: executable Memory Doctor panel for diagnostic runs, SLOs, repair plans, static checks, and structured benchmark metrics.
 *
 * [POS]
 * 个人大脑指挥中心 Memory Doctor 面板。展示静态检查、可执行诊断（含结构化 benchmark 指标卡片）、最近 diagnostic run、SLO 和 probe 级修复计划。
 */

import type { useTranslations } from 'next-intl';
import type {
  MemoryCommandBenchmarkSummary,
  MemoryCommandCenterResponse,
  MemoryCommandDiagnosticProbeResult,
  MemoryCommandDiagnosticRun,
  MemoryCommandDoctorCheck,
  MemoryCommandRepairPlan,
} from '@/services/memoryCommandCenter';

type MemoryTranslation = ReturnType<typeof useTranslations<'memory'>>;

const READINESS_STATUSES = ['ready', 'warning', 'critical', 'missing'] as const;
const DOCTOR_CHECK_IDS = [
  'relational_store',
  'memory_base_path',
  'context_bundle_manifest',
  'vector_index',
  'knowledge_graph',
  'embedding_provider',
  'event_ledger',
  'health_snapshot',
  'deployment_boundary',
  'embedding_live',
  'retrieval_pipeline',
  'sparse_cjk_recall',
  'golden_recall_benchmark',
  'memory_quality_governance',
  'migration_integrity',
] as const;
const DOCTOR_REPAIR_ACTIONS = [
  'review_storage_config',
  'enable_vector_store',
  'configure_embedding',
  'run_diagnostics',
  'run_health_refresh',
  'review_retrieval_trace',
] as const;

type ReadinessStatus = (typeof READINESS_STATUSES)[number];
type DoctorCheckId = (typeof DOCTOR_CHECK_IDS)[number];
type DoctorRepairAction = (typeof DOCTOR_REPAIR_ACTIONS)[number];
export type DoctorExecutableAction = Extract<DoctorRepairAction, 'run_diagnostics' | 'run_health_refresh'>;

const isReadinessStatus = (value: string): value is ReadinessStatus =>
  READINESS_STATUSES.includes(value as ReadinessStatus);
const isDoctorCheckId = (value: string): value is DoctorCheckId => DOCTOR_CHECK_IDS.includes(value as DoctorCheckId);
const isDoctorRepairAction = (value: string): value is DoctorRepairAction =>
  DOCTOR_REPAIR_ACTIONS.includes(value as DoctorRepairAction);
const isExecutableDoctorAction = (value: string): value is DoctorExecutableAction =>
  value === 'run_diagnostics' || value === 'run_health_refresh';

const formatTime = (value?: string | null): string =>
  value
    ? new Intl.DateTimeFormat(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }).format(new Date(value))
    : '';

const formatDuration = (value?: number | null): string => (value ? `${Math.round(value)}ms` : '-');
const formatPercent = (value: number): string => `${Math.round(value * 100)}%`;

export const MemoryDoctorPanel = ({
  snapshot,
  t,
  actionId,
  diagnosticRun,
  onDoctorAction,
}: {
  snapshot: MemoryCommandCenterResponse;
  t: MemoryTranslation;
  actionId: string | null;
  diagnosticRun: MemoryCommandDiagnosticRun | null;
  onDoctorAction: (action: DoctorExecutableAction) => void;
}) => {

  return (
  <>
    <div className="flex flex-col gap-2 rounded-lg border border-border/50 bg-background/70 p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="text-sm font-medium text-foreground">{t('commandCenter.doctorRunTitle')}</div>
      </div>
      <button
        type="button"
        disabled={actionId === 'diagnostics:run_diagnostics'}
        onClick={() => onDoctorAction('run_diagnostics')}
        className="w-full rounded-full border border-border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-60 sm:w-auto"
      >
        {t('commandCenter.doctorRunAll')}
      </button>
    </div>
    {diagnosticRun && (
      <DiagnosticRunSummary run={diagnosticRun} t={t} actionId={actionId} onDoctorAction={onDoctorAction} />
    )}
    <div className="grid gap-2 md:grid-cols-2">
      {snapshot.doctor_checks.map((check) => (
        <DoctorCheckRow key={check.id} check={check} t={t} actionId={actionId} onDoctorAction={onDoctorAction} />
      ))}
      {!snapshot.doctor_checks.length && (
        <div className="rounded-lg border border-dashed border-border/70 p-4 text-sm text-muted-foreground">
          {t('commandCenter.doctorEmpty')}
        </div>
      )}
    </div>
  </>
  );
};

const DoctorCheckRow = ({
  check,
  t,
  actionId,
  onDoctorAction,
}: {
  check: MemoryCommandDoctorCheck;
  t: MemoryTranslation;
  actionId: string | null;
  onDoctorAction: (action: DoctorExecutableAction) => void;
}) => {
  return (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="text-sm font-medium text-foreground">
          {isDoctorCheckId(check.id) ? t(`commandCenter.doctorCheck.${check.id}.label`) : check.label}
        </div>
        <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
          {isDoctorCheckId(check.id) ? t(`commandCenter.doctorCheck.${check.id}.evidence`) : check.evidence}
        </div>
      </div>
      <StatusPill status={check.status} t={t} />
    </div>
    <RepairPlanList plans={check.repair_plans} t={t} actionId={actionId} onDoctorAction={onDoctorAction} />
    <ProbeDetails
      impact={check.impact}
      nextAction={check.next_action}
      canAutoFix={check.can_auto_fix}
      safeToRetry={check.safe_to_retry}
      t={t}
    />
  </div>
  );
};

const DiagnosticRunSummary = ({
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
  if (value >= thresholds.good) return 'text-emerald-500 dark:text-emerald-400';
  if (value >= thresholds.warn) return 'text-amber-500 dark:text-amber-400';
  return 'text-red-500 dark:text-red-400';
};

const BenchmarkMetrics = ({ summary, t }: { summary: MemoryCommandBenchmarkSummary; t: MemoryTranslation }) => {
  const k = String(summary.top_k);
  const entries = Object.entries(summary.categories);

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
        <MetricCard label={t('commandCenter.benchmarkLatencyP50')} value={`${Math.round(summary.latency_p50_ms)}ms`} />
        <MetricCard label={t('commandCenter.benchmarkLatencyP95')} value={`${Math.round(summary.latency_p95_ms)}ms`} />
      </div>
      {entries.length > 0 && (
        <div>
          <div className="mb-1 text-[10px] text-muted-foreground">{t('commandCenter.benchmarkCategories')}</div>
          <div className="flex flex-wrap gap-1">
            {entries.map(([cat, ratio]) => {
              const [passed, total] = ratio.split('/').map(Number);
              const allPassed = passed === total;
              return (
                <span
                  key={cat}
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    allPassed
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                      : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                  }`}
                >
                  {cat.replace(/_/g, ' ')} {ratio}
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

const RepairPlanList = ({
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
  if (!plans.length) return null;
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

const StatusPill = ({ status, t }: { status: string; t: MemoryTranslation }) => (
  <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] ${statusClassName(status)}`}>
    {isReadinessStatus(status) ? t(`commandCenter.readinessStatus.${status}`) : status}
  </span>
);

const ProbeDetails = ({
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

const statusClassName = (status: string): string => {
  if (status === 'ready') return 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300';
  if (status === 'warning' || status === 'missing') {
    return 'border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300';
  }
  if (status === 'critical') return 'border-destructive/20 bg-destructive/10 text-destructive';
  return 'border-border bg-background text-muted-foreground';
};
