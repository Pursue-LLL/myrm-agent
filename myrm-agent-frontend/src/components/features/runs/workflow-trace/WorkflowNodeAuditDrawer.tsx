'use client';
/* oxlint-disable jsx-a11y/prefer-tag-over-role */

/**
 * WorkflowNodeAuditDrawer Component.
 * Holographic snapshot drawer for a single workflow node:
 * prompt excerpt, tools invoked, input/output payloads, 4D validation scores, and breakpoint replay trigger.
 * Adheres strictly to zero-emoji and explicit type constraints (no `any`).
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Activity,
  CheckCircle2,
  Clock,
  Code2,
  Cpu,
  FileText,
  Play,
  RotateCcw,
  ShieldCheck,
  Wrench,
  X,
} from 'lucide-react';
import {
  PayloadValue,
  WorkflowNodeSnapshot,
  WorkflowNodeStatus,
} from './workflowTraceTypes';
import { WorkflowTraceService } from './workflowTraceService';

interface WorkflowNodeAuditDrawerProps {
  isOpen: boolean;
  node: WorkflowNodeSnapshot | null;
  workflowId: string;
  onClose: () => void;
  onReplaySuccess?: () => void;
}

export const WorkflowNodeAuditDrawer: React.FC<WorkflowNodeAuditDrawerProps> = ({
  isOpen,
  node,
  workflowId,
  onClose,
  onReplaySuccess,
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('workflowTrace');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback in test suites
  }

  const [steerPrompt, setSteerPrompt] = useState<string>('');
  const [overrideInputsJson, setOverrideInputsJson] = useState<string>('');
  const [isReplaying, setIsReplaying] = useState<boolean>(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);

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

  const handleReplay = async (): Promise<void> => {
    if (!node) {
      return;
    }

    let parsedOverrides: Record<string, PayloadValue> = {};
    if (overrideInputsJson.trim()) {
      try {
        parsedOverrides = JSON.parse(overrideInputsJson) as Record<string, PayloadValue>;
      } catch {
        setFeedbackMessage('JSON 格式解析错误，请检查输入参数');
        return;
      }
    }

    setIsReplaying(true);
    setFeedbackMessage(null);
    try {
      const res = await WorkflowTraceService.replayFromNode({
        workflow_id: workflowId,
        node_id: node.node_id,
        override_inputs: parsedOverrides,
        steer_prompt: steerPrompt.trim() || null,
      });

      if (res.status === 'completed' || res.status === 'resumed') {
        setFeedbackMessage(t('replaySuccess'));
        if (onReplaySuccess) {
          onReplaySuccess();
        }
      } else {
        setFeedbackMessage(res.message || t('replayFailed'));
      }
    } finally {
      setIsReplaying(false);
    }
  };

  if (!isOpen || !node) {
    return null;
  }

  const statusBadge = getStatusBadge(node.status);
  const scores = node.validation_scores;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="node-audit-title"
      className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm"
    >
      <div className="relative w-full max-w-2xl h-full bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 font-mono text-sm font-bold">
              #{node.step_number}
            </div>
            <div>
              <h2 id="node-audit-title" className="text-base font-semibold text-slate-100 flex items-center gap-2">
                <span>{node.title}</span>
                <span className={`text-[11px] px-2 py-0.5 rounded-full border ${statusBadge.style}`}>
                  {statusBadge.label}
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5 font-mono">{node.node_id}</p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 p-6 overflow-y-auto space-y-5 bg-slate-950/30">
          {/* Quick Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs">
            <div className="flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-emerald-400" />
              <div>
                <span className="text-[10px] text-slate-500 block">耗时</span>
                <span className="font-mono text-slate-200">{node.duration_ms.toFixed(1)} ms</span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Cpu className="w-3.5 h-3.5 text-indigo-400" />
              <div>
                <span className="text-[10px] text-slate-500 block">Token 消耗</span>
                <span className="font-mono text-slate-200">{node.tokens_consumed} tok</span>
              </div>
            </div>

            <div className="flex items-center gap-2 col-span-2 sm:col-span-1">
              <Activity className="w-3.5 h-3.5 text-sky-400" />
              <div>
                <span className="text-[10px] text-slate-500 block">快照指纹</span>
                <span className="font-mono text-slate-300 text-[11px] truncate max-w-[120px] block">
                  {node.identity_hash}
                </span>
              </div>
            </div>
          </div>

          {/* 4D Validation Scorecard */}
          {scores && (
            <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  {t('validationScoreTitle')}
                </span>
                <span className="text-xs font-bold font-mono text-indigo-400">
                  {t('compositeScore')}: {(scores.composite_score * 100).toFixed(1)}%
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                <div className="p-2 rounded-lg bg-slate-900 border border-slate-800/80">
                  <span className="text-slate-500 block">{t('completeness')}</span>
                  <span className="font-mono font-semibold text-slate-200">
                    {(scores.completeness * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="p-2 rounded-lg bg-slate-900 border border-slate-800/80">
                  <span className="text-slate-500 block">{t('accuracy')}</span>
                  <span className="font-mono font-semibold text-slate-200">
                    {(scores.accuracy * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="p-2 rounded-lg bg-slate-900 border border-slate-800/80">
                  <span className="text-slate-500 block">{t('compliance')}</span>
                  <span className="font-mono font-semibold text-slate-200">
                    {(scores.compliance * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="p-2 rounded-lg bg-slate-900 border border-slate-800/80">
                  <span className="text-slate-500 block">{t('relevance')}</span>
                  <span className="font-mono font-semibold text-slate-200">
                    {(scores.relevance * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Prompt Excerpt */}
          {node.prompt_excerpt && (
            <div className="space-y-1.5">
              <span className="text-xs font-medium text-slate-400 flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-indigo-400" />
                {t('promptExcerpt')}
              </span>
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80 text-xs text-slate-300 font-sans leading-relaxed">
                {node.prompt_excerpt}
              </div>
            </div>
          )}

          {/* Tools Called */}
          {node.tools_called.length > 0 && (
            <div className="space-y-1.5">
              <span className="text-xs font-medium text-slate-400 flex items-center gap-1.5">
                <Wrench className="w-3.5 h-3.5 text-amber-400" />
                {t('toolsInvoked')}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {node.tools_called.map((tool) => (
                  <span
                    key={tool}
                    className="px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800 text-[11px] font-mono text-indigo-300"
                  >
                    {tool}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Input & Output Payloads */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div className="space-y-1.5">
              <span className="font-medium text-slate-400 flex items-center gap-1.5">
                <Code2 className="w-3.5 h-3.5 text-sky-400" />
                {t('inputPayload')}
              </span>
              <pre className="p-3 rounded-xl bg-slate-950 border border-slate-800 font-mono text-[11px] text-slate-300 overflow-x-auto whitespace-pre-wrap max-h-40">
                {JSON.stringify(node.input_payload, null, 2)}
              </pre>
            </div>

            <div className="space-y-1.5">
              <span className="font-medium text-slate-400 flex items-center gap-1.5">
                <Code2 className="w-3.5 h-3.5 text-emerald-400" />
                {t('outputPayload')}
              </span>
              <pre className="p-3 rounded-xl bg-slate-950 border border-slate-800 font-mono text-[11px] text-slate-300 overflow-x-auto whitespace-pre-wrap max-h-40">
                {JSON.stringify(node.output_payload, null, 2)}
              </pre>
            </div>
          </div>

          {/* Breakpoint Replay Sandbox Controller */}
          <div className="p-4 rounded-xl bg-indigo-950/20 border border-indigo-900/40 space-y-3">
            <span className="text-xs font-semibold text-indigo-200 flex items-center gap-1.5">
              <RotateCcw className="w-4 h-4 text-indigo-400" />
              断点自愈干预与重放
            </span>

            <div className="space-y-2">
              <input
                type="text"
                value={steerPrompt}
                onChange={(e) => {
                  setSteerPrompt(e.target.value);
                }}
                placeholder={t('steerPromptPlaceholder')}
                className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />

              <textarea
                value={overrideInputsJson}
                onChange={(e) => {
                  setOverrideInputsJson(e.target.value);
                }}
                placeholder={t('overrideInputPlaceholder')}
                rows={2}
                className="w-full p-2.5 rounded-lg bg-slate-950 border border-slate-800 font-mono text-xs text-slate-300 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={handleReplay}
                disabled={isReplaying}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium shadow transition-all active:scale-95"
              >
                <Play className="w-3.5 h-3.5" />
                <span>{isReplaying ? t('replayingBtn') : t('replayFromNodeBtn')}</span>
              </button>

              {feedbackMessage && (
                <span className="text-[11px] text-emerald-300 flex items-center gap-1 animate-in fade-in">
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                  <span>{feedbackMessage}</span>
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
