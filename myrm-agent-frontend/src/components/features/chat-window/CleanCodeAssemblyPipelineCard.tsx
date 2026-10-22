import React, { useState } from 'react';
import {
  Layers,
  CheckCircle2,
  AlertOctagon,
  ArrowRight,
  ShieldAlert,
  ShieldCheck,
  FileCode2,
  X,
  Play,
  RotateCcw,
} from 'lucide-react';
import type {
  CleanCodeAssemblyPipelineCardProps,
  CleanCodeTaskItem,
  PipelineStage,
} from './clean-code-pipeline/types';
import {
  MOCK_INITIAL_TASK,
  PIPELINE_STAGES,
} from './clean-code-pipeline/types';

export const CleanCodeAssemblyPipelineCard: React.FC<CleanCodeAssemblyPipelineCardProps> = ({
  taskId = 'clean-task-101',
  sessionId = 'sess-default',
  initialTask = MOCK_INITIAL_TASK,
  onDismiss,
  onAdvanceComplete,
}) => {
  const [task, setTask] = useState<CleanCodeTaskItem>(initialTask);
  const [selectedStage, setSelectedStage] = useState<PipelineStage>(task.currentStage);
  const [isAdvancing, setIsAdvancing] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const currentStageIndex = PIPELINE_STAGES.findIndex((s) => s.stage === task.currentStage);

  const handleAdvance = () => {
    setIsAdvancing(true);
    setStatusMessage('Validating architectural boundaries via AST linter...');

    setTimeout(() => {
      if (task.status === 'blocked') {
        setStatusMessage('Stage progression blocked: please resolve architectural boundary violations first.');
        setIsAdvancing(false);
        return;
      }

      const nextIndex = currentStageIndex + 1;
      if (nextIndex < PIPELINE_STAGES.length) {
        const nextStage = PIPELINE_STAGES[nextIndex].stage;
        const updatedTask: CleanCodeTaskItem = {
          ...task,
          currentStage: nextStage,
          stageHistory: [...task.stageHistory, nextStage],
          artifacts: {
            ...task.artifacts,
            [task.currentStage]: {
              stage: task.currentStage,
              title: `${PIPELINE_STAGES[currentStageIndex].label} Artifact`,
              content: `Deliverable produced by ${PIPELINE_STAGES[currentStageIndex].label}. AST static verification passed.`,
            },
          },
        };
        setTask(updatedTask);
        setSelectedStage(nextStage);
        setStatusMessage(`Successfully advanced to ${PIPELINE_STAGES[nextIndex].label}.`);
        if (onAdvanceComplete) {
          onAdvanceComplete(updatedTask);
        }
      } else {
        const completedTask: CleanCodeTaskItem = {
          ...task,
          status: 'completed',
        };
        setTask(completedTask);
        setStatusMessage('Clean-Code pipeline successfully completed all 5 stages!');
        if (onAdvanceComplete) {
          onAdvanceComplete(completedTask);
        }
      }
      setIsAdvancing(false);
    }, 400);
  };

  const handleTriggerSimulatedViolation = () => {
    const violatingTask: CleanCodeTaskItem = {
      ...task,
      status: 'blocked',
      violations: [
        {
          sourceModule: 'src.domain.payment',
          targetModule: 'src.ui.views.invoice_view',
          violationType: 'inverted_dependency',
          ruleDescription: "Domain layer 'src.domain.payment' cannot import outer presentation layer 'src.ui.views.invoice_view'.",
          remediationSuggestion: "Apply DIP: declare an abstract PaymentPresenterProtocol in 'src.domain.payment' and implement it in UI layer.",
        },
      ],
    };
    setTask(violatingTask);
    setStatusMessage('Architecture Linter Gate: Inverted dependency detected! Pipeline BLOCKED.');
  };

  const handleClearViolations = () => {
    const clearedTask: CleanCodeTaskItem = {
      ...task,
      status: 'running',
      violations: [],
    };
    setTask(clearedTask);
    setStatusMessage('Violations resolved with Dependency Inversion Principle. Gate opened.');
  };

  const selectedArtifact = task.artifacts[selectedStage];

  return (
    <section
      aria-label="Clean-Code Assembly Pipeline"
      className="flex flex-col border rounded-xl bg-card text-card-foreground shadow-sm overflow-hidden my-3 max-w-4xl border-border"
    >
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 bg-muted/40 border-b border-border">
        <div className="flex items-center gap-2.5">
          <Layers className="w-5 h-5 text-indigo-500" />
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              Clean-Code Assembly Pipeline
              <span className="text-xs px-2 py-0.5 rounded-full font-mono bg-indigo-500/10 text-indigo-500 border border-indigo-500/20">
                {task.taskId}
              </span>
            </h3>
            <p className="text-xs text-muted-foreground line-clamp-1">{task.title}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {task.status === 'blocked' ? (
            <span className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-full font-medium bg-red-500/10 text-red-500 border border-red-500/20">
              <ShieldAlert className="w-3.5 h-3.5" />
              Gate Blocked
            </span>
          ) : task.status === 'completed' ? (
            <span className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-full font-medium bg-green-500/10 text-green-500 border border-green-500/20">
              <ShieldCheck className="w-3.5 h-3.5" />
              All Stages Done
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-full font-medium bg-blue-500/10 text-blue-500 border border-blue-500/20">
              <Play className="w-3.5 h-3.5" />
              In Progress
            </span>
          )}
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              aria-label="Close Clean-Code pipeline card"
              className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </header>

      {/* 5-Stage Stepper Bar */}
      <div className="grid grid-cols-5 border-b border-border bg-background">
        {PIPELINE_STAGES.map((s, idx) => {
          const isDone = task.stageHistory.includes(s.stage) && s.stage !== task.currentStage;
          const isCurrent = s.stage === task.currentStage;
          const isSelected = s.stage === selectedStage;

          return (
            <button
              key={s.stage}
              type="button"
              onClick={() => {
                setSelectedStage(s.stage);
              }}
              className={`flex flex-col items-center justify-center py-2.5 px-2 text-center border-r last:border-r-0 border-border transition-colors ${
                isSelected ? 'bg-primary/5 font-semibold text-foreground' : 'text-muted-foreground hover:bg-muted/30'
              }`}
            >
              <div className="flex items-center gap-1.5 mb-1">
                {isDone ? (
                  <CheckCircle2 className="w-4 h-4 text-green-500" />
                ) : isCurrent ? (
                  task.status === 'blocked' ? (
                    <AlertOctagon className="w-4 h-4 text-red-500" />
                  ) : (
                    <div className="w-4 h-4 rounded-full border-2 border-indigo-500 flex items-center justify-center">
                      <div className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                    </div>
                  )
                ) : (
                  <div className="w-4 h-4 rounded-full border border-muted-foreground/40 text-[10px] flex items-center justify-center">
                    {idx + 1}
                  </div>
                )}
                <span className="text-xs truncate">{s.label.split('. ')[1]}</span>
              </div>
              <span className="text-[10px] text-muted-foreground line-clamp-1">
                {isDone ? 'Completed' : isCurrent ? (task.status === 'blocked' ? 'Blocked' : 'Active') : 'Queued'}
              </span>
            </button>
          );
        })}
      </div>

      {/* Main Content Area */}
      <div className="p-4 space-y-4">
        {/* Architecture Violations Banner */}
        {task.violations.length > 0 && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg space-y-2">
            <div className="flex items-center justify-between text-xs font-semibold text-red-500">
              <span className="flex items-center gap-1.5">
                <AlertOctagon className="w-4 h-4" />
                Architecture Boundary Violations ({task.violations.length})
              </span>
              <button
                type="button"
                onClick={handleClearViolations}
                className="flex items-center gap-1 text-[11px] underline hover:text-red-400"
              >
                <RotateCcw className="w-3 h-3" />
                Apply DIP Fix
              </button>
            </div>
            <div className="space-y-1.5">
              {task.violations.map((v, i) => (
                <div key={i} className="text-xs bg-background/80 p-2.5 rounded border border-red-500/20 text-foreground space-y-1">
                  <div className="flex items-center gap-1 font-mono text-[11px] text-red-400">
                    <span>{v.sourceModule}</span>
                    <ArrowRight className="w-3 h-3" />
                    <span>{v.targetModule}</span>
                  </div>
                  <p className="text-muted-foreground text-[11px]">{v.ruleDescription}</p>
                  <p className="text-indigo-400 text-[11px] font-medium">💡 Recommendation: {v.remediationSuggestion}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Selected Stage Detail & Artifact View */}
        <div className="bg-muted/20 border border-border rounded-lg p-3.5 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileCode2 className="w-4 h-4 text-indigo-400" />
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Stage Detail: {PIPELINE_STAGES.find((s) => s.stage === selectedStage)?.label}
              </h4>
            </div>
            <span className="text-[11px] text-muted-foreground">
              {PIPELINE_STAGES.find((s) => s.stage === selectedStage)?.roleDescription}
            </span>
          </div>

          {selectedArtifact ? (
            <div className="space-y-1 bg-background p-3 rounded border border-border text-xs">
              <div className="font-medium text-foreground">{selectedArtifact.title}</div>
              <p className="text-muted-foreground whitespace-pre-wrap">{selectedArtifact.content}</p>
            </div>
          ) : (
            <div className="py-4 text-center text-xs text-muted-foreground">
              No deliverable artifact produced for this stage yet.
            </div>
          )}
        </div>

        {/* Status notification banner */}
        {statusMessage && (
          <output aria-live="polite" className="block text-xs px-3 py-2 rounded bg-muted text-muted-foreground border border-border">
            {statusMessage}
          </output>
        )}
      </div>

      {/* Footer Controls */}
      <footer className="flex items-center justify-between px-4 py-3 bg-muted/40 border-t border-border">
        <button
          type="button"
          onClick={handleTriggerSimulatedViolation}
          className="text-xs text-muted-foreground hover:text-red-400 transition-colors"
        >
          Simulate Violation
        </button>

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={isAdvancing || task.status === 'completed' || task.status === 'blocked'}
            onClick={handleAdvance}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              task.status === 'completed'
                ? 'bg-muted text-muted-foreground cursor-not-allowed'
                : task.status === 'blocked'
                ? 'bg-red-500/20 text-red-400 cursor-not-allowed border border-red-500/30'
                : 'bg-primary text-primary-foreground hover:bg-primary/90'
            }`}
          >
            {isAdvancing ? (
              'Verifying...'
            ) : task.status === 'completed' ? (
              'Pipeline Finished'
            ) : (
              <>
                Advance Stage
                <ArrowRight className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        </div>
      </footer>
    </section>
  );
};
