/**
 * [INPUT] TypedActionPayload, isOpen, onConfirm, onCancel, isExecuting
 * [OUTPUT] TypedActionPreviewModal component providing pre-flight scope review and confirmation gate
 * [POS] task-action-preview/TypedActionPreviewModal.tsx
 */

'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  AlertTriangle,
  ShieldAlert,
  FileText,
  ArrowRight,
  CheckCircle2,
  X,
  Layers,
  Activity,
  Lock,
} from 'lucide-react';
import type {
  TypedActionPayload,
  TypedActionRiskLevel,
  TypedActionCategory,
} from './taskActionPreviewTypes';

export interface TypedActionPreviewModalProps {
  action: TypedActionPayload | null;
  isOpen: boolean;
  onConfirm: (action: TypedActionPayload) => void;
  onCancel: () => void;
  isExecuting?: boolean;
}

const RISK_BADGE_MAP: Record<
  TypedActionRiskLevel,
  { label: string; badgeClass: string; borderClass: string }
> = {
  low: {
    label: '低风险操作',
    badgeClass: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
    borderClass: 'border-border',
  },
  moderate: {
    label: '中度风险',
    badgeClass: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30',
    borderClass: 'border-amber-500/30',
  },
  high: {
    label: '高危变更',
    badgeClass: 'bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/30',
    borderClass: 'border-orange-500/40',
  },
  critical: {
    label: 'CRITICAL · 危险不可逆',
    badgeClass: 'bg-destructive/10 text-destructive border-destructive/40',
    borderClass: 'border-destructive/60',
  },
};

const CATEGORY_LABEL_MAP: Record<TypedActionCategory, string> = {
  goal_lifecycle: '目标生命周期变更',
  file_mutation: '文件批量写入/覆写',
  deployment: '线上构建发布',
  permission_grant: '权限提升与授权',
  batch_cleanup: '批量资源清理',
};

export const TypedActionPreviewModal: React.FC<TypedActionPreviewModalProps> = ({
  action,
  isOpen,
  onConfirm,
  onCancel,
  isExecuting = false,
}) => {
  const [confirmationChecked, setConfirmationChecked] = useState<boolean>(false);
  const [confirmKeyword, setConfirmKeyword] = useState<string>('');

  useEffect(() => {
    if (isOpen) {
      setConfirmationChecked(false);
      setConfirmKeyword('');
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || isExecuting) {
      return;
    }
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel();
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => {
      window.removeEventListener('keydown', handleGlobalKeyDown);
    };
  }, [isOpen, isExecuting, onCancel]);

  if (!isOpen || !action) {
    return null;
  }

  const isCritical = action.riskLevel === 'critical';
  const requiresGate = isCritical || Boolean(action.requiresExplicitConfirmation);
  const canConfirm = !requiresGate || (confirmationChecked && (!isCritical || confirmKeyword.trim().toUpperCase() === 'CONFIRM'));
  const riskMeta = RISK_BADGE_MAP[action.riskLevel];

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="typed-action-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto animate-in fade-in duration-150 m-0 h-full w-full max-w-none max-h-none border-0"
    >
      <div
        className={`w-full max-w-xl rounded-xl border bg-card text-card-foreground shadow-2xl overflow-hidden transition-all ${riskMeta.borderClass}`}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b px-5 py-4">
          <div className="flex items-center gap-3">
            <div
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border ${riskMeta.badgeClass}`}
            >
              {isCritical ? (
                <ShieldAlert className="h-5 w-5" />
              ) : (
                <AlertTriangle className="h-5 w-5" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3
                  id="typed-action-modal-title"
                  className="text-base font-semibold text-foreground tracking-tight"
                >
                  {action.title}
                </h3>
                <span
                  className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-semibold ${riskMeta.badgeClass}`}
                >
                  {riskMeta.label}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {CATEGORY_LABEL_MAP[action.category]} · 资源 ID: {action.targetResourceId}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            disabled={isExecuting}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            aria-label="关闭预览"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="max-h-[60vh] overflow-y-auto px-5 py-4 space-y-4 text-xs">
          {/* Description */}
          <div className="rounded-lg bg-muted/40 p-3 border border-border/50">
            <p className="text-foreground leading-relaxed">{action.description}</p>
          </div>

          {/* Affected Files */}
          {action.affectedFiles && action.affectedFiles.length > 0 && (
            <div className="space-y-1.5">
              <span className="flex items-center gap-1.5 font-medium text-foreground">
                <FileText className="h-3.5 w-3.5 text-primary" />
                受影响文件范围 ({action.affectedFiles.length})
              </span>
              <div className="max-h-28 overflow-y-auto rounded-md border bg-muted/20 p-2 font-mono text-[11px] space-y-1">
                {action.affectedFiles.map((file) => {
                  return (
                    <div key={file} className="flex items-center gap-1.5 text-muted-foreground">
                      <span className="h-1.5 w-1.5 rounded-full bg-primary/60 shrink-0" />
                      <span className="truncate">{file}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Quota Delta */}
          {action.quotaDelta && action.quotaDelta.length > 0 && (
            <div className="space-y-1.5">
              <span className="flex items-center gap-1.5 font-medium text-foreground">
                <Layers className="h-3.5 w-3.5 text-primary" />
                资源与配额变更预估
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {action.quotaDelta.map((q) => {
                  return (
                    <div
                      key={q.metric}
                      className="flex items-center justify-between rounded border bg-muted/20 px-2.5 py-1.5 text-[11px]"
                    >
                      <span className="text-muted-foreground font-mono">{q.metric}</span>
                      <div className="flex items-center gap-1 font-mono font-medium">
                        <span className="line-through text-muted-foreground">{q.before}</span>
                        <ArrowRight className="h-3 w-3 text-primary shrink-0" />
                        <span className="text-foreground">{q.after}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Side Effects */}
          {action.sideEffects && action.sideEffects.length > 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 space-y-1.5">
              <span className="flex items-center gap-1.5 font-medium text-amber-600 dark:text-amber-400">
                <Activity className="h-3.5 w-3.5" />
                潜在副作用与不可逆风险
              </span>
              <ul className="list-disc list-inside space-y-1 text-muted-foreground">
                {action.sideEffects.map((side) => {
                  return <li key={side}>{side}</li>;
                })}
              </ul>
            </div>
          )}

          {/* Confirmation Gate */}
          {requiresGate && (
            <div className="space-y-3 pt-2 border-t border-border/60">
              <label className="flex items-start gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={confirmationChecked}
                  onChange={(e) => {
                    setConfirmationChecked(e.target.checked);
                  }}
                  className="mt-0.5 h-3.5 w-3.5 rounded border-muted-foreground/40 text-primary focus:ring-primary"
                />
                <span className="text-foreground font-medium">
                  我已充分知悉以上变更范围及潜在风险，确认继续执行该操作
                </span>
              </label>

              {isCritical && (
                <div className="space-y-1 pl-5.5">
                  <div className="flex items-center gap-1.5 text-muted-foreground text-[11px]">
                    <Lock className="h-3 w-3 text-destructive" />
                    请输入 <span className="font-mono font-bold text-destructive">CONFIRM</span> 解除高危锁死门限：
                  </div>
                  <input
                    type="text"
                    value={confirmKeyword}
                    onChange={(e) => {
                      setConfirmKeyword(e.target.value);
                    }}
                    placeholder="输入 CONFIRM"
                    className="w-full rounded-md border border-input bg-background px-2.5 py-1 text-xs font-mono focus:border-destructive focus:ring-1 focus:ring-destructive outline-none"
                  />
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t px-5 py-3 bg-muted/20">
          <button
            type="button"
            onClick={onCancel}
            disabled={isExecuting}
            className="rounded-lg border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => {
              if (canConfirm) {
                onConfirm(action);
              }
            }}
            disabled={!canConfirm || isExecuting}
            className={`inline-flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-xs font-semibold text-white transition-all shadow-sm ${
              isCritical
                ? 'bg-destructive hover:bg-destructive/90 focus:ring-destructive'
                : 'bg-primary hover:bg-primary/90 focus:ring-primary'
            } disabled:opacity-40 disabled:cursor-not-allowed`}
          >
            {isExecuting ? (
              <span className="flex items-center gap-1.5">
                <span className="h-3.5 w-3.5 rounded-full border-2 border-white/40 border-t-white animate-spin" />
                正在下发并生成回执...
              </span>
            ) : (
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5" />
                确认并下发执行
              </span>
            )}
          </button>
        </div>
      </div>
    </dialog>
  );
};
