/**
 * [INPUT]
 * ProjectSwitchHandshakeResponse from workspaceBoundaryTypes.ts
 * [OUTPUT]
 * BoundaryHandshakeCard: Zero-risk project switch handshake card verifying target directory safety.
 * [POS]
 * src/components/features/workspace-boundary/BoundaryHandshakeCard.tsx
 */

import React from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  Ban,
  Check,
  X,
  Folder,
  GitBranch,
} from 'lucide-react';
import { ProjectSwitchHandshakeResponse } from './workspaceBoundaryTypes';

export interface BoundaryHandshakeCardProps {
  handshake: ProjectSwitchHandshakeResponse;
  onConfirmSwitch: (handshakeToken: string) => void;
  onCancelSwitch: () => void;
  className?: string;
}

export const BoundaryHandshakeCard: React.FC<BoundaryHandshakeCardProps> = ({
  handshake,
  onConfirmSwitch,
  onCancelSwitch,
  className = '',
}) => {
  const renderRiskBadge = () => {
    if (handshake.risk_level === 'blocked') {
      return (
        <span
          data-testid="risk-badge-blocked"
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-950/80 text-rose-300 border border-rose-800"
        >
          <Ban className="w-3.5 h-3.5" />
          Blocked
        </span>
      );
    }
    if (handshake.risk_level === 'warning') {
      return (
        <span
          data-testid="risk-badge-warning"
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-950/80 text-amber-300 border border-amber-800"
        >
          <AlertTriangle className="w-3.5 h-3.5" />
          Warning
        </span>
      );
    }
    return (
      <span
        data-testid="risk-badge-safe"
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-800"
      >
        <ShieldCheck className="w-3.5 h-3.5" />
        Safe Handshake
      </span>
    );
  };

  return (
    <div
      data-testid="boundary-handshake-card"
      className={`bg-zinc-900 border border-zinc-700/80 rounded-xl p-4 shadow-xl text-xs font-mono space-y-3 ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-indigo-400" />
          <span className="font-semibold text-zinc-100 text-sm">
            Project Switch Boundary Handshake
          </span>
        </div>
        {renderRiskBadge()}
      </div>

      <p className="text-zinc-400 text-[11px] leading-relaxed">
        Read-only probe verified the target workspace environment before aligning context.
      </p>

      {/* Target Directory & Branch Inspector */}
      <div className="bg-zinc-950 p-2.5 rounded-lg border border-zinc-800/80 space-y-2">
        <div className="flex items-start gap-2">
          <Folder className="w-3.5 h-3.5 text-zinc-400 mt-0.5 shrink-0" />
          <div className="min-w-0 flex-1">
            <span className="text-zinc-500 text-[10px] block">Target Directory:</span>
            <span
              data-testid="target-path-display"
              className="text-zinc-200 break-all select-all font-mono"
            >
              {handshake.target_path}
            </span>
          </div>
        </div>

        {handshake.is_git_repo ? (
          <div className="flex items-center gap-2 pt-1 border-t border-zinc-900">
            <GitBranch className="w-3.5 h-3.5 text-purple-400 shrink-0" />
            <div className="flex items-center gap-2 flex-wrap text-zinc-300">
              <span>
                Branch: <strong className="text-zinc-100">{handshake.git_branch || 'HEAD'}</strong>
              </span>
              {handshake.git_uncommitted_changes > 0 ? (
                <span
                  data-testid="target-dirty-changes"
                  className="text-amber-400 text-[11px] bg-amber-950/60 px-1.5 py-0.5 rounded border border-amber-800/60"
                >
                  {handshake.git_uncommitted_changes} uncommitted files
                </span>
              ) : (
                <span className="text-emerald-400 text-[11px]">Working tree clean</span>
              )}
            </div>
          </div>
        ) : null}
      </div>

      {/* Warnings List */}
      {handshake.warnings.length > 0 ? (
        <div
          data-testid="handshake-warnings"
          className="bg-amber-950/30 border border-amber-900/60 rounded-lg p-2.5 space-y-1 text-amber-200"
        >
          {handshake.warnings.map((warning, idx) => (
            <div key={idx} className="flex items-start gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
              <span className="text-[11px] leading-tight">{warning}</span>
            </div>
          ))}
        </div>
      ) : null}

      {/* Action Buttons */}
      <div className="flex items-center justify-end gap-2 pt-1">
        <button
          type="button"
          data-testid="handshake-cancel-btn"
          onClick={onCancelSwitch}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 transition"
        >
          <X className="w-3.5 h-3.5" />
          Keep Current Workspace
        </button>

        <button
          type="button"
          data-testid="handshake-confirm-btn"
          onClick={() => onConfirmSwitch(handshake.handshake_token)}
          disabled={!handshake.can_switch}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition ${
            handshake.can_switch
              ? 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-900/20'
              : 'bg-zinc-800 text-zinc-500 border border-zinc-700/60 cursor-not-allowed'
          }`}
        >
          <Check className="w-3.5 h-3.5" />
          Align & Switch Project
        </button>
      </div>
    </div>
  );
};
