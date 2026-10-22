'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  Sparkles,
  RotateCcw,
  GitBranch,
  Wrench,
  CheckCircle2,
  ExternalLink,
} from 'lucide-react';

export type GapCategory =
  | 'missing_handoff_metadata'
  | 'missing_approval_gate'
  | 'missing_publish_artifact'
  | 'missing_verification_step';

export type GapSeverity = 'info' | 'warning' | 'error';

export type StepStage =
  | 'routing'
  | 'analysis'
  | 'execution'
  | 'review'
  | 'verification'
  | 'delivery';

export interface HandoffMetadataData {
  source_agent: string;
  target_agent: string;
  transfer_reason: string;
  context_keys?: string[];
}

export interface HandoffStepData {
  step_id: string;
  stage: StepStage;
  agent_role: string;
  requires_approval: boolean;
  requires_verification: boolean;
  produced_artifacts: string[];
  metadata?: HandoffMetadataData | null;
}

export interface HandoffGapDiagnosticData {
  rule_id: string;
  category: GapCategory;
  severity: GapSeverity;
  step_id: string;
  message: string;
  suggested_fix: string;
}

export interface DecisionChainLinkData {
  step_id: string;
  from_role: string;
  to_role: string;
  stage: StepStage;
  reason: string;
}

export interface PipelineDefinitionData {
  pipeline_id: string;
  name: string;
  steps: HandoffStepData[];
  version: string;
}

export interface PipelineIntegrityDoctorReportData {
  pipeline_id: string;
  total_steps: number;
  is_healthy: boolean;
  gaps: HandoffGapDiagnosticData[];
  decision_chain: DecisionChainLinkData[];
  scanned_at: number;
}

export interface PipelineIntegrityDoctorCardProps {
  chatId?: string;
  initialPipeline?: PipelineDefinitionData | null;
  onDismiss?: () => void;
}

function createHealthySample(chatId: string): PipelineDefinitionData {
  return {
    pipeline_id: `pipe-${chatId}-healthy`,
    name: 'Sample Compliant Full-Lifecycle Pipeline',
    steps: [
      {
        step_id: 'step-route',
        stage: 'routing',
        agent_role: 'orchestrator',
        requires_approval: false,
        requires_verification: false,
        produced_artifacts: [],
      },
      {
        step_id: 'step-code',
        stage: 'execution',
        agent_role: 'coder',
        requires_approval: false,
        requires_verification: true,
        produced_artifacts: [],
        metadata: {
          source_agent: 'orchestrator',
          target_agent: 'coder',
          transfer_reason: 'Execute required task features',
        },
      },
      {
        step_id: 'step-review',
        stage: 'review',
        agent_role: 'reviewer',
        requires_approval: true,
        requires_verification: false,
        produced_artifacts: [],
        metadata: {
          source_agent: 'coder',
          target_agent: 'reviewer',
          transfer_reason: 'Peer review and approval gate',
        },
      },
      {
        step_id: 'step-deploy',
        stage: 'delivery',
        agent_role: 'deployer',
        requires_approval: false,
        requires_verification: false,
        produced_artifacts: ['distribution_bundle.zip'],
        metadata: {
          source_agent: 'reviewer',
          target_agent: 'deployer',
          transfer_reason: 'Publish production release',
        },
      },
    ],
    version: '1.0.0',
  };
}

function createGappedSample(chatId: string): PipelineDefinitionData {
  return {
    pipeline_id: `pipe-${chatId}-gapped`,
    name: 'Gapped Pipeline (Missing Metadata & Approval)',
    steps: [
      {
        step_id: 'step-arch',
        stage: 'analysis',
        agent_role: 'architect',
        requires_approval: false,
        requires_verification: false,
        produced_artifacts: [],
      },
      {
        step_id: 'step-impl',
        stage: 'execution',
        agent_role: 'coder',
        requires_approval: false,
        requires_verification: false,
        produced_artifacts: [],
        // Missing handoff metadata!
      },
      {
        step_id: 'step-publish',
        stage: 'delivery',
        agent_role: 'deployer',
        requires_approval: false, // Missing approval gate!
        requires_verification: false, // Missing verification step!
        produced_artifacts: [], // Missing publish artifact!
        metadata: {
          source_agent: 'coder',
          target_agent: 'deployer',
          transfer_reason: 'Immediate release',
        },
      },
    ],
    version: '0.9.0',
  };
}

function lintClientPipeline(pipeline: PipelineDefinitionData): PipelineIntegrityDoctorReportData {
  const gaps: HandoffGapDiagnosticData[] = [];
  const steps = pipeline.steps;
  const hasDelivery = steps.some((s) => s.stage === 'delivery');
  const hasApproval = steps.some((s) => s.requires_approval || s.stage === 'review');
  const hasVerification = steps.some((s) => s.requires_verification || s.stage === 'verification');

  let prevStep: HandoffStepData | null = null;
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    if (i > 0 && prevStep && step.agent_role !== prevStep.agent_role) {
      if (!step.metadata || !step.metadata.transfer_reason?.trim()) {
        gaps.push({
          rule_id: 'RULE-001-HANDOFF-METADATA',
          category: 'missing_handoff_metadata',
          severity: 'warning',
          step_id: step.step_id,
          message: `Step '${step.step_id}' handoff from '${prevStep.agent_role}' to '${step.agent_role}' lacks metadata.`,
          suggested_fix: `Declare HandoffMetadata with source_agent='${prevStep.agent_role}' and target_agent='${step.agent_role}'.`,
        });
      }
    }

    if (step.stage === 'delivery' && step.produced_artifacts.length === 0) {
      gaps.push({
        rule_id: 'RULE-003-PUBLISH-ARTIFACT',
        category: 'missing_publish_artifact',
        severity: 'error',
        step_id: step.step_id,
        message: `Delivery step '${step.step_id}' produces no declared publish artifacts.`,
        suggested_fix: 'Attach at least one artifact identifier to produced_artifacts.',
      });
    }

    prevStep = step;
  }

  if (hasDelivery && !hasApproval) {
    gaps.push({
      rule_id: 'RULE-002-APPROVAL-GATE',
      category: 'missing_approval_gate',
      severity: 'error',
      step_id: 'step-delivery',
      message: 'Pipeline proceeds directly to Delivery without an explicit approval or review gate.',
      suggested_fix: 'Insert an IN_REVIEW stage or set requires_approval=true before final delivery.',
    });
  }

  if (hasDelivery && !hasVerification) {
    gaps.push({
      rule_id: 'RULE-004-VERIFICATION-STEP',
      category: 'missing_verification_step',
      severity: 'warning',
      step_id: 'step-delivery',
      message: 'Pipeline reaches Delivery without a preceding verification or testing step.',
      suggested_fix: 'Add a verification step or set requires_verification=true on the execution step.',
    });
  }

  const decisionChain: DecisionChainLinkData[] = steps.map((s, idx) => ({
    step_id: s.step_id,
    from_role: s.metadata?.source_agent || (idx === 0 ? 'user' : steps[idx - 1].agent_role),
    to_role: s.agent_role,
    stage: s.stage,
    reason: s.metadata?.transfer_reason || `Advance to stage ${s.stage}`,
  }));

  const isHealthy = !gaps.some((g) => g.severity === 'error');

  return {
    pipeline_id: pipeline.pipeline_id,
    total_steps: steps.length,
    is_healthy: isHealthy,
    gaps,
    decision_chain: decisionChain,
    scanned_at: Date.now() / 1000,
  };
}

export function PipelineIntegrityDoctorCard({
  chatId = 'default-chat-session',
  initialPipeline = null,
  onDismiss,
}: PipelineIntegrityDoctorCardProps) {
  const [pipeline, setPipeline] = useState<PipelineDefinitionData>(() => {
    return initialPipeline || createHealthySample(chatId);
  });
  const [report, setReport] = useState<PipelineIntegrityDoctorReportData>(() => {
    return lintClientPipeline(initialPipeline || createHealthySample(chatId));
  });
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    if (initialPipeline) {
      setPipeline(initialPipeline);
      setReport(lintClientPipeline(initialPipeline));
    }
  }, [initialPipeline]);

  const handleRunLint = useCallback(() => {
    const newReport = lintClientPipeline(pipeline);
    setReport(newReport);
    setStatusMessage(
      `Lint complete: ${newReport.gaps.length} gaps detected across ${newReport.total_steps} steps.`
    );
  }, [pipeline]);

  const handleLoadGappedSample = useCallback(() => {
    const gapped = createGappedSample(chatId);
    setPipeline(gapped);
    const newReport = lintClientPipeline(gapped);
    setReport(newReport);
    setStatusMessage('Loaded sample flawed pipeline with multiple integrity gaps.');
  }, [chatId]);

  const handleAutoHeal = useCallback(() => {
    const healedSteps: HandoffStepData[] = pipeline.steps.map((step, idx) => {
      const prevRole = idx === 0 ? 'user' : pipeline.steps[idx - 1].agent_role;
      let meta = step.metadata;
      if (idx > 0 && (!meta || !meta.transfer_reason?.trim())) {
        meta = {
          source_agent: prevRole,
          target_agent: step.agent_role,
          transfer_reason: `Auto-healed delegation to ${step.agent_role}`,
          context_keys: ['task_spec'],
        };
      }

      let reqApproval = step.requires_approval;
      let reqVerif = step.requires_verification;
      let artifacts = [...step.produced_artifacts];

      if (step.stage === 'delivery') {
        reqApproval = true;
        if (artifacts.length === 0) {
          artifacts = [`artifact_${step.step_id}_auto_bundle.tar.gz`];
        }
      } else if (step.stage === 'execution' || step.stage === 'analysis') {
        reqVerif = true;
      }

      return {
        ...step,
        requires_approval: reqApproval,
        requires_verification: reqVerif,
        produced_artifacts: artifacts,
        metadata: meta,
      };
    });

    const healedPipeline: PipelineDefinitionData = {
      ...pipeline,
      name: `${pipeline.name} (Auto-Healed)`,
      version: `${pipeline.version}+healed`,
      steps: healedSteps,
    };

    setPipeline(healedPipeline);
    const newReport = lintClientPipeline(healedPipeline);
    setReport(newReport);
    setStatusMessage('Auto-healed pipeline: all blocking error gaps remediated!');
  }, [pipeline]);

  const handleReset = useCallback(() => {
    const healthy = createHealthySample(chatId);
    setPipeline(healthy);
    setReport(lintClientPipeline(healthy));
    setStatusMessage('Reset to standard compliant pipeline.');
  }, [chatId]);

  return (
    <dialog
      open
      className="relative flex flex-col w-full max-w-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl shadow-lg p-5 text-zinc-900 dark:text-zinc-100 z-50 overflow-hidden"
      data-testid="pipeline-integrity-doctor-card"
    >
      <div className="flex items-center justify-between pb-3 border-b border-zinc-200 dark:border-zinc-800">
        <div className="flex items-center space-x-2">
          <ShieldCheck className="w-5 h-5 text-indigo-500" />
          <h3 className="font-semibold text-base">Pipeline Integrity Doctor Pack</h3>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            aria-label="Dismiss dialog"
            className="text-xs px-2.5 py-1 rounded bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300 transition-colors"
          >
            Dismiss
          </button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 my-4">
        <div className="flex flex-col p-3 rounded-lg bg-zinc-50 dark:bg-zinc-800/40 border border-zinc-200 dark:border-zinc-700">
          <span className="text-xs text-zinc-500 font-medium">Total Steps</span>
          <span className="text-xl font-bold mt-1" data-testid="stat-total-steps">
            {report.total_steps}
          </span>
        </div>
        <div className="flex flex-col p-3 rounded-lg bg-amber-50/60 dark:bg-amber-950/30 border border-amber-200/60 dark:border-amber-800/50">
          <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">
            Detected Gaps
          </span>
          <span className="text-xl font-bold mt-1" data-testid="stat-detected-gaps">
            {report.gaps.length}
          </span>
        </div>
        <div
          className={`flex flex-col p-3 rounded-lg border ${
            report.is_healthy
              ? 'bg-emerald-50/60 dark:bg-emerald-950/30 border-emerald-200/60 dark:border-emerald-800/50 text-emerald-700 dark:text-emerald-300'
              : 'bg-rose-50/60 dark:bg-rose-950/30 border-rose-200/60 dark:border-rose-800/50 text-rose-700 dark:text-rose-300'
          }`}
        >
          <span className="text-xs font-medium">Health Status</span>
          <span className="text-base font-bold mt-1" data-testid="stat-health-status">
            {report.is_healthy ? 'HEALTHY' : 'CRITICAL ISSUES'}
          </span>
        </div>
      </div>

      {statusMessage && (
        <output
          className="text-xs p-2.5 rounded-lg mb-3 flex items-center space-x-2 border bg-zinc-100 dark:bg-zinc-800/60 border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300"
          data-testid="status-message"
        >
          <Sparkles className="w-4 h-4 text-indigo-500 shrink-0" />
          <span>{statusMessage}</span>
        </output>
      )}

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <button
          onClick={handleRunLint}
          className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white font-medium transition-colors"
          data-testid="btn-run-lint"
        >
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Run Integrity Lint</span>
        </button>
        <button
          onClick={handleLoadGappedSample}
          className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-md bg-amber-600 hover:bg-amber-700 text-white font-medium transition-colors"
          data-testid="btn-load-gapped"
        >
          <AlertTriangle className="w-3.5 h-3.5" />
          <span>Load Gapped Sample</span>
        </button>
        <button
          onClick={handleAutoHeal}
          className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white font-medium transition-colors"
          data-testid="btn-auto-heal"
        >
          <Wrench className="w-3.5 h-3.5" />
          <span>Auto-Heal Gaps</span>
        </button>
        <button
          onClick={handleReset}
          className="flex items-center space-x-1.5 text-xs px-2.5 py-1.5 rounded-md bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300 font-medium transition-colors"
          data-testid="btn-reset"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Reset</span>
        </button>
      </div>

      <div className="space-y-2 mb-3">
        <div className="flex items-center space-x-1.5 text-xs font-semibold text-zinc-500 uppercase tracking-wider">
          <GitBranch className="w-3.5 h-3.5" />
          <span>Inspectable Decision Chain ({report.decision_chain.length})</span>
        </div>
        <div
          className="p-2.5 rounded-lg bg-zinc-50 dark:bg-zinc-800/40 border border-zinc-200 dark:border-zinc-800 text-xs space-y-1.5 max-h-28 overflow-y-auto"
          data-testid="decision-chain-list"
        >
          {report.decision_chain.map((link) => (
            <div
              key={link.step_id}
              className="flex items-center justify-between text-zinc-600 dark:text-zinc-300"
              data-testid={`chain-link-${link.step_id}`}
            >
              <span className="font-mono font-medium">
                [{link.stage.toUpperCase()}] {link.from_role} → {link.to_role}
              </span>
              <span className="text-[11px] text-zinc-400 truncate max-w-[200px]" title={link.reason}>
                {link.reason}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-2 mb-2 max-h-40 overflow-y-auto">
        <div className="flex items-center space-x-1.5 text-xs font-semibold text-zinc-500 uppercase tracking-wider">
          <AlertTriangle className="w-3.5 h-3.5" />
          <span>Integrity Diagnostics ({report.gaps.length})</span>
        </div>
        {report.gaps.length === 0 ? (
          <div
            className="flex items-center justify-center space-x-2 text-xs text-emerald-600 dark:text-emerald-400 py-3"
            data-testid="empty-gaps"
          >
            <CheckCircle2 className="w-4 h-4" />
            <span>All pipeline handoffs, approval gates & verification steps pass integrity checks.</span>
          </div>
        ) : (
          <div className="space-y-1.5" data-testid="gaps-list">
            {report.gaps.map((gap) => (
              <div
                key={`${gap.rule_id}-${gap.step_id}`}
                className={`p-2.5 rounded-md border text-xs ${
                  gap.severity === 'error'
                    ? 'bg-rose-50 dark:bg-rose-950/40 border-rose-300 dark:border-rose-800 text-rose-800 dark:text-rose-200'
                    : 'bg-amber-50 dark:bg-amber-950/40 border-amber-300 dark:border-amber-800 text-amber-800 dark:text-amber-200'
                }`}
                data-testid={`gap-item-${gap.rule_id}`}
              >
                <div className="flex items-center justify-between font-semibold mb-1">
                  <span>[{gap.severity.toUpperCase()}] {gap.rule_id}</span>
                  <span className="text-[11px] opacity-75">{gap.category}</span>
                </div>
                <div className="mb-1">{gap.message}</div>
                <div className="text-[11px] opacity-80 flex items-center space-x-1">
                  <ExternalLink className="w-3 h-3 shrink-0" />
                  <span>Fix: {gap.suggested_fix}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </dialog>
  );
}
