'use client';

/**
 * WorkflowSwimlaneViewer Component.
 * Dynamic 5-stage workflow execution swimlane visualizer:
 * intake -> planning -> dispatch -> execution_validation -> closure.
 * Visualizes ordered DAG nodes, status badges, token usage, and triggers node holographic drawer.
 * Adheres strictly to zero-emoji and explicit type constraints (no `any`).
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Activity,
  CheckCircle2,
  ChevronRight,
  Clock,
  Cpu,
  GitBranch,
  Layers,
  RefreshCw,
  ShieldCheck,
  Workflow,
} from 'lucide-react';
import {
  WorkflowNodeSnapshot,
  WorkflowNodeStatus,
  WorkflowStage,
  WorkflowTraceResponse,
} from './workflowTraceTypes';
import { WorkflowTraceService } from './workflowTraceService';
import { WorkflowNodeAuditDrawer } from './WorkflowNodeAuditDrawer';

interface WorkflowSwimlaneViewerProps {
  workflowId: string;
  className?: string;
}

export const WorkflowSwimlaneViewer: React.FC<WorkflowSwimlaneViewerProps> = ({
  workflowId,
  className = '',
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('workflowTrace');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback in test suites
  }

  const [trace, setTrace] = useState<WorkflowTraceResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [selectedNode, setSelectedNode] = useState<WorkflowNodeSnapshot | null>(null);

  const fetchTrace = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    try {
      const data = await WorkflowTraceService.getWorkflowTrace(workflowId);
      setTrace(data);
    } finally {
      setIsLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    fetchTrace();
  }, [fetchTrace]);

  const getStageLabel = (stage: WorkflowStage): string => {
    switch (stage) {
      case 'intake':
        return t('stageIntake');
      case 'planning':
        return t('stagePlanning');
      case 'dispatch':
        return t('stageDispatch');
      case 'execution_validation':
        return t('stageExecution');
      case 'closure':
      default:
        return t('stageClosure');
    }
  };

  const getStatusBadge = (status: WorkflowNodeStatus): { label: string; style: string } => {
    switch (status) {
      case 'completed':
        return { label: t('statusCompleted'), style: 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300' };
      case 'running':
        return { label: t('statusRunning'), style: 'bg-sky-500/15 border-sky-500/30 text-sky-300 animate-pulse' };
      case 'replaying':
        return { label: t('statusReplaying'), style: 'bg-indigo-500/15 border-indigo-500/30 text-indigo-300 animate-pulse' };
      case 'failed':
        return { label: t('statusFailed'), style: 'bg-rose-500/15 border-rose-500/30 text-rose-300' };
      case 'retrying':
        return { label: t('statusRetrying'), style: 'bg-amber-500/15 border-amber-500/30 text-amber-300' };
      case 'pending':
      default:
        return { label: t('statusPending'), style: 'bg-slate-800 border-slate-700 text-slate-400' };
    }
  };

  if (!trace && isLoading) {
    return (
      <div className="p-8 rounded-2xl bg-slate-900 border border-slate-800 text-center text-xs text-slate-400 flex items-center justify-center gap-2">
        <RefreshCw className="w-4 h-4 animate-spin text-indigo-400" />
        <span>加载工作流执行链路中...</span>
      </div>
    );
  }

  if (!trace) {
    return null;
  }

  return (
    <div className={`p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-6 ${className}`}>
      {/* Title & KPI Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-5 border-b border-slate-800">
        <div>
          <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2.5">
            <Workflow className="w-5 h-5 text-indigo-400" />
            <span>{trace.title}</span>
          </h3>
          <p className="text-xs text-slate-400 mt-1">{t('subtitle')}</p>
        </div>

        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800">
            <Cpu className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-slate-400">{t('totalTokens')}:</span>
            <strong className="font-mono text-slate-200">{trace.total_tokens}</strong>
          </div>

          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800">
            <Clock className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-slate-400">{t('totalDuration')}:</span>
            <strong className="font-mono text-slate-200">{trace.total_duration_ms.toFixed(0)} ms</strong>
          </div>

          <button
            type="button"
            onClick={fetchTrace}
            disabled={isLoading}
            aria-label="Refresh workflow trace"
            className="p-1.5 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-indigo-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* 5-Stage Swimlane Track */}
      <div className="space-y-3">
        <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
          <span className="flex items-center gap-1.5">
            <Layers className="w-4 h-4 text-sky-400" />
            <span>执行链路五阶泳道 (点击节点查看全息审计与断点重放)</span>
          </span>
          <span className="text-[11px] font-mono text-slate-500">Nodes: {trace.nodes.length}</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          {trace.nodes.map((node, idx) => {
            const statusBadge = getStatusBadge(node.status);
            const isLast = idx === trace.nodes.length - 1;

            return (
              <div key={node.node_id} className="relative flex flex-col justify-between">
                <button
                  type="button"
                  onClick={() => {
                    setSelectedNode(node);
                  }}
                  className="w-full text-left p-4 rounded-xl bg-slate-950/80 border border-slate-800 hover:border-indigo-500/60 hover:bg-slate-950 transition-all space-y-3 shadow-sm group focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  {/* Node Header */}
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-mono font-bold text-indigo-400">
                      Step #{node.step_number}
                    </span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium border ${statusBadge.style}`}>
                      {statusBadge.label}
                    </span>
                  </div>

                  {/* Node Title & Stage */}
                  <div>
                    <h4 className="text-xs font-semibold text-slate-200 group-hover:text-indigo-300 transition-colors line-clamp-1">
                      {node.title}
                    </h4>
                    <span className="text-[10px] text-slate-500 mt-0.5 block">
                      {getStageLabel(node.stage)}
                    </span>
                  </div>

                  {/* 4D Score & Duration Footnote */}
                  <div className="pt-2 border-t border-slate-900 flex items-center justify-between text-[10px] text-slate-400">
                    <span className="flex items-center gap-1 font-mono">
                      <Clock className="w-3 h-3 text-emerald-400" />
                      {node.duration_ms.toFixed(0)}ms
                    </span>

                    {node.validation_scores && (
                      <span className="flex items-center gap-1 font-mono text-indigo-300 font-medium">
                        <ShieldCheck className="w-3 h-3 text-indigo-400" />
                        {(node.validation_scores.composite_score * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                </button>

                {/* Connector arrow between sequential nodes */}
                {!isLast && (
                  <div className="hidden md:flex absolute -right-2 top-1/2 -translate-y-1/2 z-10 text-slate-700 pointer-events-none">
                    <ChevronRight className="w-4 h-4" />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Node Holographic Audit Drawer */}
      <WorkflowNodeAuditDrawer
        isOpen={selectedNode !== null}
        node={selectedNode}
        workflowId={workflowId}
        onClose={() => {
          setSelectedNode(null);
        }}
        onReplaySuccess={() => {
          fetchTrace();
        }}
      />
    </div>
  );
};
