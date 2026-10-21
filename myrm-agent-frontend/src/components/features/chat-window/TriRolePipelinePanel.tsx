'use client';

import React, { useState } from 'react';
import {
  ShieldCheck,
  ClipboardList,
  Code2,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronUp,
  X,
  FileCheck2,
  ArrowRight,
  PackageCheck,
} from 'lucide-react';

export type TriRoleType = 'planner' | 'generator' | 'evaluator';
export type StageStatus = 'planned' | 'generating' | 'evaluating' | 'accepted' | 'rejected';

export interface AcceptanceCriterionData {
  criterion_id: string;
  description: string;
  assertion_rule: string;
  is_satisfied: boolean;
}

export interface EvaluationVerdictData {
  is_accepted: boolean;
  score: number;
  evaluator_notes: string;
  criteria_results: Record<string, boolean>;
  evaluated_at: string;
}

export interface ArtifactManifestData {
  manifest_id: string;
  session_id: string;
  stage_index: number;
  produced_files: string[];
  passed_assertions: string[];
  key_constraints: string[];
  pending_todos: string[];
  created_at: string;
}

export interface TriRolePipelineStageData {
  stage_id: string;
  stage_name: string;
  status: StageStatus;
  planner_output?: string;
  criteria: AcceptanceCriterionData[];
  generator_output?: string;
  produced_files: string[];
  evaluation?: EvaluationVerdictData | null;
  manifest?: ArtifactManifestData | null;
}

export interface TriRoleSessionData {
  session_id: string;
  task_description: string;
  stages: TriRolePipelineStageData[];
  current_stage_index: number;
  is_completed: boolean;
  created_at: string;
  updated_at: string;
}

export interface TriRolePipelinePanelProps {
  session: TriRoleSessionData;
  onClose?: () => void;
  onAdvanceStage?: () => void;
  onExportManifest?: (manifest: ArtifactManifestData) => void;
  className?: string;
}

const STATUS_BADGE_MAP: Record<StageStatus, { label: string; bg: string; text: string }> = {
  planned: { label: 'Planning', bg: 'bg-sky-500/10', text: 'text-sky-400 border-sky-500/30' },
  generating: { label: 'Generating', bg: 'bg-amber-500/10', text: 'text-amber-400 border-amber-500/30' },
  evaluating: { label: 'Evaluating', bg: 'bg-purple-500/10', text: 'text-purple-400 border-purple-500/30' },
  accepted: { label: 'Accepted', bg: 'bg-emerald-500/10', text: 'text-emerald-400 border-emerald-500/30' },
  rejected: { label: 'Rejected', bg: 'bg-rose-500/10', text: 'text-rose-400 border-rose-500/30' },
};

export const TriRolePipelinePanel: React.FC<TriRolePipelinePanelProps> = ({
  session,
  onClose,
  onAdvanceStage,
  onExportManifest,
  className = '',
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(true);

  const currentStage = session.stages[session.current_stage_index] || session.stages[0];
  const stageStatus = currentStage?.status || 'planned';
  const badge = STATUS_BADGE_MAP[stageStatus];

  const handleExport = () => {
    if (currentStage?.manifest && onExportManifest) {
      onExportManifest(currentStage.manifest);
    }
  };

  return (
    <div
      className={`border border-border/80 rounded-xl bg-card/95 backdrop-blur-md shadow-lg overflow-hidden transition-all text-xs ${className}`}
      data-testid="tri-role-pipeline-panel"
    >
      {/* Header bar */}
      <div className="flex items-center justify-between px-3.5 py-2.5 bg-muted/40 border-b border-border/50">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          <span className="font-semibold text-foreground tracking-tight">
            Tri-Role Pipeline Separation
          </span>
          <span
            className={`px-2 py-0.5 rounded-full border text-[11px] font-medium ${badge.bg} ${badge.text}`}
          >
            {badge.label}
          </span>
          {session.is_completed && (
            <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 text-[10px] font-semibold">
              Completed
            </span>
          )}
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => {
              setIsExpanded(!isExpanded);
            }}
            className="p-1 hover:bg-muted rounded text-muted-foreground hover:text-foreground transition-colors"
            title={isExpanded ? 'Collapse' : 'Expand'}
            aria-label={isExpanded ? 'Collapse' : 'Expand'}
          >
            {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1 hover:bg-muted rounded text-muted-foreground hover:text-foreground transition-colors"
              title="Close panel"
              aria-label="Close panel"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Main Content Body */}
      {isExpanded && (
        <div className="p-3.5 space-y-3.5">
          {/* Task Description & Stage Indicator */}
          <div className="flex items-center justify-between pb-2 border-b border-border/40">
            <div>
              <p className="font-medium text-foreground truncate max-w-sm">
                {session.task_description}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Stage {session.current_stage_index + 1} of {session.stages.length}:{' '}
                <span className="text-foreground/90 font-medium">{currentStage?.stage_name}</span>
              </p>
            </div>

            {currentStage?.status === 'accepted' && onAdvanceStage && !session.is_completed && (
              <button
                type="button"
                onClick={onAdvanceStage}
                className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white font-medium shadow-sm transition-colors text-[11px]"
              >
                Advance <ArrowRight className="w-3 h-3" />
              </button>
            )}
          </div>

          {/* Tri-Role Separation Columns */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Planner Role Box */}
            <div className="p-2.5 rounded-lg border border-sky-500/20 bg-sky-500/5 space-y-2">
              <div className="flex items-center gap-1.5 font-medium text-sky-400">
                <ClipboardList className="w-3.5 h-3.5" />
                <span>1. Planner Criteria</span>
              </div>
              <p className="text-muted-foreground line-clamp-2">
                {currentStage?.planner_output || 'Awaiting planner breakdown...'}
              </p>
              {currentStage?.criteria && currentStage.criteria.length > 0 && (
                <div className="space-y-1 pt-1">
                  {currentStage.criteria.map((crit) => (
                    <div
                      key={crit.criterion_id}
                      className="flex items-start gap-1 text-[11px] text-foreground/80 bg-background/50 px-2 py-1 rounded"
                    >
                      <span className="font-mono text-sky-300">[{crit.criterion_id}]</span>
                      <span className="truncate">{crit.description}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Generator Role Box */}
            <div className="p-2.5 rounded-lg border border-amber-500/20 bg-amber-500/5 space-y-2">
              <div className="flex items-center gap-1.5 font-medium text-amber-400">
                <Code2 className="w-3.5 h-3.5" />
                <span>2. Generator Deliverables</span>
              </div>
              <p className="text-muted-foreground line-clamp-2">
                {currentStage?.generator_output || 'Awaiting implementation deliverable...'}
              </p>
              {currentStage?.produced_files && currentStage.produced_files.length > 0 && (
                <div className="space-y-1 pt-1">
                  {currentStage.produced_files.map((file) => (
                    <div
                      key={file}
                      className="flex items-center gap-1 text-[11px] text-foreground/80 font-mono bg-background/50 px-2 py-1 rounded truncate"
                    >
                      <FileCheck2 className="w-3 h-3 text-amber-400 shrink-0" />
                      <span className="truncate">{file}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Evaluator Role Box */}
            <div className="p-2.5 rounded-lg border border-purple-500/20 bg-purple-500/5 space-y-2">
              <div className="flex items-center justify-between font-medium text-purple-400">
                <div className="flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>3. Independent Evaluator</span>
                </div>
                {currentStage?.evaluation && (
                  <span className="font-bold font-mono">
                    {(currentStage.evaluation.score * 100).toFixed(0)}%
                  </span>
                )}
              </div>
              {currentStage?.evaluation ? (
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5 font-medium text-[11px]">
                    {currentStage.evaluation.is_accepted ? (
                      <span className="flex items-center gap-1 text-emerald-400">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Accepted
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-rose-400">
                        <XCircle className="w-3.5 h-3.5" /> Rejected
                      </span>
                    )}
                  </div>
                  <p className="text-muted-foreground text-[11px] line-clamp-2">
                    {currentStage.evaluation.evaluator_notes}
                  </p>
                </div>
              ) : (
                <p className="text-muted-foreground">Pending objective verification...</p>
              )}
            </div>
          </div>

          {/* Artifact Manifest Handoff Bar */}
          {currentStage?.manifest && (
            <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300">
              <div className="flex items-center gap-2">
                <PackageCheck className="w-4 h-4 text-emerald-400" />
                <span>
                  Handoff Manifest: <strong>{currentStage.manifest.manifest_id}</strong> (
                  {currentStage.manifest.produced_files.length} deliverables,{' '}
                  {currentStage.manifest.passed_assertions.length} assertions verified)
                </span>
              </div>
              {onExportManifest && (
                <button
                  type="button"
                  onClick={handleExport}
                  className="px-2 py-0.5 rounded border border-emerald-500/40 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-200 transition-colors text-[11px]"
                >
                  Export Handoff
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default TriRolePipelinePanel;
