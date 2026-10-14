/**
 * [INPUT]
 * StructuredApprovalRequest, DecisionKind from visualDiffTypes.ts
 * [OUTPUT]
 * VisualDiffApprovalCard: Interactive rich diff and command risk approval card with hotkey support.
 * [POS]
 * src/components/approval/visual-diff/VisualDiffApprovalCard.tsx
 */

import React, { useEffect, useRef } from 'react';
import {
  FileCode,
  Terminal,
  Check,
  X,
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  Bookmark,
  Layers,
} from 'lucide-react';
import { DecisionKind, StructuredApprovalRequest } from './visualDiffTypes';

export interface VisualDiffApprovalCardProps {
  request: StructuredApprovalRequest;
  onDecision: (decision: DecisionKind) => void;
  isFocused?: boolean;
  className?: string;
}

export const VisualDiffApprovalCard: React.FC<VisualDiffApprovalCardProps> = ({
  request,
  onDecision,
  isFocused = false,
  className = '',
}) => {
  const cardRef = useRef<HTMLDivElement>(null);

  // Keyboard shortcut listener: 1 or Y for allow, 2 or N for reject, 3 for remember
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Only process when target card or active element is not inside an input/textarea
      const activeElement = document.activeElement;
      const isInput =
        activeElement instanceof HTMLInputElement ||
        activeElement instanceof HTMLTextAreaElement;

      if (isInput) {
        return;
      }

      // Check if card has focus or is focused by parent
      const cardHasFocus =
        cardRef.current?.contains(activeElement) || isFocused;

      if (!cardHasFocus) {
        return;
      }

      const key = event.key.toLowerCase();
      if (key === '1' || key === 'y') {
        event.preventDefault();
        onDecision('allow');
      } else if (key === '2' || key === 'n') {
        event.preventDefault();
        onDecision('reject');
      } else if (key === '3') {
        event.preventDefault();
        onDecision('remember_session');
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isFocused, onDecision]);

  const renderRiskSeverityBadge = (severity: string) => {
    if (severity === 'critical') {
      return (
        <span
          data-testid="risk-badge-critical"
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-950 text-rose-300 border border-rose-800"
        >
          <ShieldAlert className="w-3.5 h-3.5" />
          Critical Risk
        </span>
      );
    }
    if (severity === 'high') {
      return (
        <span
          data-testid="risk-badge-high"
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-orange-950 text-orange-300 border border-orange-800"
        >
          <AlertTriangle className="w-3.5 h-3.5" />
          High Risk
        </span>
      );
    }
    if (severity === 'medium') {
      return (
        <span
          data-testid="risk-badge-medium"
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-950 text-amber-300 border border-amber-800"
        >
          <AlertTriangle className="w-3.5 h-3.5" />
          Medium Risk
        </span>
      );
    }
    return (
      <span
        data-testid="risk-badge-low"
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800"
      >
        <CheckCircle2 className="w-3.5 h-3.5" />
        Low Risk
      </span>
    );
  };

  return (
    <section
      ref={cardRef}
      aria-label="Structured Approval Card"
      data-testid="visual-diff-approval-card"
      className={`bg-zinc-900 border rounded-xl p-4 shadow-xl text-xs font-mono select-none outline-none transition-all ${
        isFocused
          ? 'border-indigo-500 ring-2 ring-indigo-500/30'
          : 'border-zinc-700/80 hover:border-zinc-600 focus:border-indigo-500'
      } ${className}`}
    >
      {/* Header bar */}
      <div className="flex items-center justify-between gap-2 pb-2.5 border-b border-zinc-800">
        <div className="flex items-center gap-2 min-w-0">
          {request.kind === 'file_write' ? (
            <FileCode className="w-4 h-4 text-sky-400 shrink-0" />
          ) : (
            <Terminal className="w-4 h-4 text-purple-400 shrink-0" />
          )}
          <span
            data-testid="approval-summary-title"
            className="font-semibold text-zinc-100 text-sm truncate"
          >
            {request.summary}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[10px] text-zinc-500">#{request.sequence_id}</span>
          {request.command_risk
            ? renderRiskSeverityBadge(request.command_risk.risk_severity)
            : null}
        </div>
      </div>

      {/* Mode A: File Write Diff Section */}
      {request.file_diff ? (
        <div
          data-testid="file-diff-section"
          className="mt-3 space-y-2"
        >
          <div className="flex items-center justify-between text-[11px] text-zinc-400">
            <span className="font-semibold text-zinc-200">
              {request.file_diff.file_path}
            </span>
            <div className="flex items-center gap-2">
              <span
                data-testid="diff-lines-added"
                className="text-emerald-400 bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/60"
              >
                +{request.file_diff.added_lines}
              </span>
              <span
                data-testid="diff-lines-removed"
                className="text-rose-400 bg-rose-950/60 px-1.5 py-0.5 rounded border border-rose-800/60"
              >
                -{request.file_diff.removed_lines}
              </span>
            </div>
          </div>

          {/* Unified Diff View Window */}
          <div
            data-testid="unified-diff-view"
            className="bg-zinc-950 p-2.5 rounded-lg border border-zinc-800 overflow-x-auto max-h-56 text-[11px] font-mono leading-relaxed"
          >
            {request.file_diff.unified_diff.split('\n').map((line, idx) => {
              if (line.startsWith('+') && !line.startsWith('+++')) {
                return (
                  <div
                    key={idx}
                    className="bg-emerald-950/40 text-emerald-300 px-1 rounded-sm whitespace-pre"
                  >
                    {line}
                  </div>
                );
              }
              if (line.startsWith('-') && !line.startsWith('---')) {
                return (
                  <div
                    key={idx}
                    className="bg-rose-950/40 text-rose-300 px-1 rounded-sm whitespace-pre"
                  >
                    {line}
                  </div>
                );
              }
              if (line.startsWith('@@')) {
                return (
                  <div
                    key={idx}
                    className="text-sky-400 bg-sky-950/30 px-1 my-0.5 rounded-sm whitespace-pre"
                  >
                    {line}
                  </div>
                );
              }
              return (
                <div key={idx} className="text-zinc-400 px-1 whitespace-pre">
                  {line}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* Mode B: Command Risk Section */}
      {request.command_risk ? (
        <div
          data-testid="command-risk-section"
          className="mt-3 space-y-2.5"
        >
          <div className="bg-zinc-950 p-2 rounded border border-zinc-800 font-mono text-zinc-100 break-all select-all">
            {request.command_risk.command}
          </div>

          <div className="space-y-1">
            <div className="text-zinc-400 text-[10px] flex items-center gap-1">
              <Layers className="w-3 h-3 text-amber-400" />
              <span>Blast Radius & Impacts:</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {request.command_risk.blast_radius_paths.map((path, idx) => (
                <span
                  key={idx}
                  data-testid="blast-path-badge"
                  className="bg-zinc-800 px-1.5 py-0.5 rounded text-[10px] text-zinc-300"
                >
                  {path}
                </span>
              ))}
            </div>
          </div>

          {request.command_risk.risk_reasons.length > 0 ? (
            <div
              data-testid="command-violations"
              className="bg-amber-950/20 border border-amber-900/60 p-2 rounded text-[11px] text-amber-300 space-y-0.5"
            >
              {request.command_risk.risk_reasons.map((reason, idx) => (
                <div key={idx} className="flex items-start gap-1">
                  <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0 mt-0.5" />
                  <span>{reason}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Decision actions with Hotkey labels */}
      <div className="flex items-center justify-between gap-2 mt-4 pt-3 border-t border-zinc-800">
        <span className="text-[10px] text-zinc-500 hidden sm:inline">
          Tab: Switch card | 1: Allow | 2: Reject | 3: Remember
        </span>

        <div className="flex items-center gap-2 ml-auto">
          {request.allowed_decisions.includes('remember_session') ? (
            <button
              type="button"
              data-testid="decision-remember-btn"
              onClick={() => onDecision('remember_session')}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition text-[11px]"
              title="Remember this decision for current session (Hotkey: 3)"
            >
              <Bookmark className="w-3 h-3 text-zinc-400" />
              <span>Remember</span>
              <kbd className="ml-1 px-1 py-0.2 bg-zinc-900 rounded text-[9px] text-zinc-400 border border-zinc-700">
                3
              </kbd>
            </button>
          ) : null}

          <button
            type="button"
            data-testid="decision-reject-btn"
            onClick={() => onDecision('reject')}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-rose-800 bg-rose-950/40 hover:bg-rose-900/50 text-rose-300 transition text-[11px]"
            title="Reject action (Hotkey: 2 or N)"
          >
            <X className="w-3.5 h-3.5 text-rose-400" />
            <span>Reject</span>
            <kbd className="ml-1 px-1 py-0.2 bg-rose-950 rounded text-[9px] text-rose-300 border border-rose-800">
              2/N
            </kbd>
          </button>

          <button
            type="button"
            data-testid="decision-allow-btn"
            onClick={() => onDecision('allow')}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg font-medium bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-950/40 transition text-[11px]"
            title="Allow action (Hotkey: 1 or Y)"
          >
            <Check className="w-3.5 h-3.5 text-white" />
            <span>Approve</span>
            <kbd className="ml-1 px-1 py-0.2 bg-emerald-700 rounded text-[9px] text-emerald-100 border border-emerald-600">
              1/Y
            </kbd>
          </button>
        </div>
      </div>
    </section>
  );
};
