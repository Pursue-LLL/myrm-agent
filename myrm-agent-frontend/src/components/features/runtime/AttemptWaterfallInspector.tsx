'use client';

/**
 * AttemptWaterfallInspector Component.
 * Visual waterfall timeline and throughput inspector for individual execution attempts.
 * Attempt telemetry and fault diagnostics with zero emojis.
 */

import React, { useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock, FileCode, RotateCw, XCircle, Zap } from 'lucide-react';
import { AttemptRecord } from './runtimeProjectionTypes';

interface AttemptWaterfallInspectorProps {
  attempts: AttemptRecord[];
}

export const AttemptWaterfallInspector: React.FC<AttemptWaterfallInspectorProps> = ({ attempts }) => {
  const [expandedAttemptId, setExpandedAttemptId] = useState<string | null>(
    attempts.find((a) => a.status === 'failed')?.attempt_id || null,
  );

  if (attempts.length === 0) {
    return (
      <div className="p-6 text-center text-xs text-slate-400 bg-slate-900/40 rounded-lg border border-slate-800">
        No attempts recorded for this Run.
      </div>
    );
  }

  return (
    <div className="space-y-3" aria-label="Attempt Waterfall Timeline">
      {attempts.map((att) => {
        const isFailed = att.status === 'failed';
        const isCompleted = att.status === 'completed';
        const isExpanded = expandedAttemptId === att.attempt_id;

        return (
          <div
            key={att.attempt_id}
            className={`rounded-lg border transition-all ${
              isFailed
                ? 'border-red-900/50 bg-red-950/20'
                : isCompleted
                  ? 'border-emerald-900/50 bg-emerald-950/20'
                  : 'border-slate-800 bg-slate-900/40'
            }`}
          >
            {/* Header / Summary Bar */}
            <button
              type="button"
              aria-expanded={isExpanded}
              onClick={() => {
                setExpandedAttemptId(isExpanded ? null : att.attempt_id);
              }}
              className="flex w-full items-center justify-between p-3.5 text-start cursor-pointer select-none"
            >
              <span className="flex items-center gap-2.5">
                {isCompleted ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                ) : isFailed ? (
                  <XCircle className="h-4 w-4 text-red-400 shrink-0" />
                ) : (
                  <RotateCw className="h-4 w-4 text-amber-400 animate-spin shrink-0" />
                )}
                <span className="text-xs font-semibold text-slate-200">Attempt #{att.attempt_number}</span>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full font-mono uppercase tracking-wider ${
                    isCompleted
                      ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-800'
                      : isFailed
                        ? 'bg-red-950/80 text-red-300 border border-red-800'
                        : 'bg-amber-950/80 text-amber-300 border border-amber-800'
                  }`}
                >
                  {att.status}
                </span>
              </span>

              {/* Watermark Telemetry */}
              <span className="flex items-center gap-4 text-xs font-mono text-slate-400">
                {att.duration_ms ? (
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3 text-slate-400" />
                    <span>{(att.duration_ms / 1000).toFixed(1)}s</span>
                  </span>
                ) : null}

                {att.tokens_per_sec > 0 ? (
                  <span className="flex items-center gap-1 text-indigo-400">
                    <Zap className="h-3 w-3" />
                    <span>{att.tokens_per_sec.toFixed(1)} tok/s</span>
                  </span>
                ) : null}

                <span className="text-[11px] text-slate-400">{att.tokens_in + att.tokens_out} tokens</span>
              </span>
            </button>

            {/* Diagnostic Details Accordion */}
            {isExpanded ? (
              <div className="px-3.5 pb-3.5 pt-1 border-t border-slate-800/80 space-y-2.5 text-xs">
                {/* Failure Reason */}
                {att.error_reason ? (
                  <div className="p-2.5 rounded bg-red-950/40 border border-red-900/60 text-red-300">
                    <div className="flex items-center gap-1.5 font-semibold text-[11px] mb-1">
                      <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
                      <span>Fault Diagnostic Reason:</span>
                    </div>
                    <p className="font-mono text-[11px] leading-relaxed break-all">{att.error_reason}</p>
                  </div>
                ) : null}

                {/* Diff Summary */}
                {att.diff_summary ? (
                  <div className="flex items-center gap-1.5 text-slate-400 text-[11px]">
                    <FileCode className="h-3.5 w-3.5 text-indigo-400" />
                    <span>Workspace Impact: {att.diff_summary}</span>
                  </div>
                ) : null}

                {/* Stack Trace */}
                {att.stack_trace ? (
                  <pre className="p-2 rounded bg-slate-950 border border-slate-800 text-[10px] font-mono text-slate-400 overflow-x-auto">
                    {att.stack_trace}
                  </pre>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
};
