'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::MemoryCommandCenterResponse (POS: Frontend Personal Brain Command Center client)
 *
 * [OUTPUT]
 * MemoryDoctorPanel: executable Memory Doctor panel for diagnostic runs, SLOs, repair plans, static checks, and structured benchmark metrics.
 *
 * [POS]
 * 个人大脑指挥中心 Memory Doctor 面板。展示静态检查、可执行诊断（含结构化 benchmark 指标卡片）、最近 diagnostic run、SLO 和 probe 级修复计划。
 */

import type {
  MemoryCommandCenterResponse,
  MemoryCommandDiagnosticHistoryItem,
  MemoryCommandDiagnosticRun,
  MemoryCommandDoctorCheck,
} from '@/services/memory/commandCenter';
import { type DoctorExecutableAction, type MemoryTranslation, isDoctorCheckId } from './memoryDoctorModel';
import { StatusPill } from './MemoryDoctorStatusPill';
import { DiagnosticTrendSection } from './MemoryDoctorTrend';
import { DiagnosticRunSummary, ProbeDetails, RepairPlanList } from './MemoryDoctorRunSection';

export const MemoryDoctorPanel = ({
  snapshot,
  t,
  actionId,
  diagnosticRun,
  diagnosticHistory,
  onDoctorAction,
}: {
  snapshot: MemoryCommandCenterResponse;
  t: MemoryTranslation;
  actionId: string | null;
  diagnosticRun: MemoryCommandDiagnosticRun | null;
  diagnosticHistory: MemoryCommandDiagnosticHistoryItem[];
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
      {diagnosticHistory.length > 0 && <DiagnosticTrendSection history={diagnosticHistory} t={t} />}
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
