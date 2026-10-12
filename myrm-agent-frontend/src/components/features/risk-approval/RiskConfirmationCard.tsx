/**
 * Tiered Risk HITL Confirmation & Dry-Run Preview Card Component.
 *
 * [INPUT] RiskConfirmationCardProps (evaluation, callbacks)
 * [OUTPUT] JSX.Element - Interactive high-visibility risk gate card
 * [POS] Item 29 frontend implementation. Strictly under 350 lines. Zero `any`.
 */

import React, { useState, useId } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  Play,
  RotateCcw,
  Check,
  X,
  Edit3,
  Eye,
  Terminal,
} from 'lucide-react';
import type {
  RiskConfirmationCardProps,
  DryRunSimulationResult,
} from './riskApprovalTypes';

export const RiskConfirmationCard: React.FC<RiskConfirmationCardProps> = ({
  evaluation,
  onConfirm,
  onReject,
  onSimulateDryRun,
  className = '',
}) => {
  const cardId = useId();
  const [isEditing, setIsEditing] = useState(false);
  const [editedJson, setEditedJson] = useState(() => JSON.stringify(evaluation.param_summary, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  const [dryRunResult, setDryRunResult] = useState<DryRunSimulationResult | null>(null);

  const isHighRisk = evaluation.tier === 'HIGH_RISK';
  const isWrite = evaluation.tier === 'WRITE';
  const isRead = evaluation.tier === 'READ';

  const handleStartEdit = () => {
    setIsEditing(true);
    setJsonError(null);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditedJson(JSON.stringify(evaluation.param_summary, null, 2));
    setJsonError(null);
  };

  const handleTriggerDryRun = async () => {
    if (!onSimulateDryRun) {
      return;
    }
    setIsSimulating(true);
    try {
      let parsedParams: Record<string, unknown> = {};
      try {
        parsedParams = JSON.parse(editedJson) as Record<string, unknown>;
      } catch {
        parsedParams = { ...evaluation.param_summary };
      }
      const res = await onSimulateDryRun(evaluation.tool_name, parsedParams);
      if (res) {
        setDryRunResult(res);
      }
    } finally {
      setIsSimulating(false);
    }
  };

  const handleConfirmAction = async () => {
    if (!evaluation.confirmation_token && isHighRisk) {
      return;
    }
    setIsSubmitting(true);
    try {
      let modified: Record<string, unknown> | null = null;
      if (isEditing) {
        try {
          modified = JSON.parse(editedJson) as Record<string, unknown>;
        } catch {
          setJsonError('Invalid JSON format');
          setIsSubmitting(false);
          return;
        }
      }
      await onConfirm({
        confirmation_token: evaluation.confirmation_token ?? '',
        approved: true,
        modified_input: modified,
        reason: 'Authorized via interactive risk gate',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRejectAction = async () => {
    setIsSubmitting(true);
    try {
      await onReject(rejectReason || 'Terminated by human operator');
    } finally {
      setIsSubmitting(false);
    }
  };

  const badgeConfig = {
    HIGH_RISK: {
      bg: 'bg-red-500/10 border-red-500/30 text-red-500 dark:bg-red-950/40 dark:border-red-800',
      icon: <ShieldAlert className="w-4 h-4 text-red-500" />,
      label: 'Level 3 · 高危操作 (强制确认)',
    },
    WRITE: {
      bg: 'bg-amber-500/10 border-amber-500/30 text-amber-600 dark:bg-amber-950/40 dark:border-amber-800 dark:text-amber-400',
      icon: <AlertTriangle className="w-4 h-4 text-amber-500" />,
      label: 'Level 2 · 状态写入 (支持预演)',
    },
    READ: {
      bg: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:bg-emerald-950/40 dark:border-emerald-800 dark:text-emerald-400',
      icon: <ShieldCheck className="w-4 h-4 text-emerald-500" />,
      label: 'Level 1 · 只读操作 (自动放行)',
    },
  }[evaluation.tier];

  return (
    <article
      aria-labelledby={`risk-card-title-${cardId}`}
      className={`rounded-xl border p-4.5 my-3 shadow-sm transition-all duration-200 ${
        isHighRisk
          ? 'border-red-500/40 bg-red-50/50 dark:bg-red-950/20'
          : isWrite
          ? 'border-amber-500/40 bg-amber-50/40 dark:bg-amber-950/15'
          : 'border-slate-200 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-900/40'
      } ${className}`}
    >
      {/* 顶部标题与等级标签 */}
      <div className="flex items-center justify-between gap-3 mb-3 pb-2.5 border-b border-black/5 dark:border-white/5">
        <div className="flex items-center gap-2 min-w-0">
          <div className="p-1.5 rounded-lg bg-black/5 dark:bg-white/10 shrink-0">
            <Terminal className="w-4 h-4 text-slate-700 dark:text-slate-300" />
          </div>
          <div className="min-w-0">
            <h4
              id={`risk-card-title-${cardId}`}
              className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate"
            >
              {evaluation.tool_name}
            </h4>
            {evaluation.target_entity && (
              <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                目标对象: <span className="font-mono text-slate-700 dark:text-slate-300">{evaluation.target_entity}</span>
              </p>
            )}
          </div>
        </div>

        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${badgeConfig.bg} shrink-0`}
        >
          {badgeConfig.icon}
          {badgeConfig.label}
        </span>
      </div>

      {/* 风险警告列表 */}
      {evaluation.risk_reasons.length > 0 && (
        <div className="mb-3 space-y-1.5">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            风险告警与潜在影响
          </p>
          <ul className="space-y-1 text-xs text-red-600 dark:text-red-400 font-medium">
            {evaluation.risk_reasons.map((reason, idx) => (
              <li key={idx} className="flex items-start gap-1.5 bg-red-500/10 dark:bg-red-950/40 px-2 py-1 rounded">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 参数结构展示或编辑器 */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            {isEditing ? '修改执行参数 (JSON)' : '参数摘要'}
          </span>
          {!isRead && !isEditing && (
            <button
              type="button"
              onClick={handleStartEdit}
              className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
            >
              <Edit3 className="w-3 h-3" />
              修改参数
            </button>
          )}
        </div>

        {isEditing ? (
          <div className="space-y-2">
            <textarea
              value={editedJson}
              onChange={(e) => {
                setEditedJson(e.target.value);
                setJsonError(null);
              }}
              rows={4}
              className="w-full text-xs font-mono p-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            {jsonError && <p className="text-xs text-red-500 font-medium">{jsonError}</p>}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={handleCancelEdit}
                className="px-2.5 py-1 text-xs rounded border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                取消
              </button>
            </div>
          </div>
        ) : (
          <div className="bg-white/80 dark:bg-slate-950/60 rounded-lg p-2.5 border border-black/5 dark:border-white/5 font-mono text-xs max-h-36 overflow-y-auto space-y-1">
            {Object.entries(evaluation.param_summary).length > 0 ? (
              Object.entries(evaluation.param_summary).map(([key, val]) => (
                <div key={key} className="flex items-baseline gap-2">
                  <span className="text-slate-500 shrink-0">{key}:</span>
                  <span className="text-slate-800 dark:text-slate-200 break-all">{val}</span>
                </div>
              ))
            ) : (
              <span className="text-slate-400">无输入参数</span>
            )}
          </div>
        )}
      </div>

      {/* Dry-Run 预演视图 */}
      {dryRunResult && (
        <div className="mb-3 p-2.5 rounded-lg border border-blue-500/30 bg-blue-50/50 dark:bg-blue-950/30 text-xs text-blue-900 dark:text-blue-300">
          <div className="flex items-center gap-1.5 font-semibold mb-1">
            <Eye className="w-3.5 h-3.5" />
            <span>Dry-Run 预演模拟结果</span>
          </div>
          <p className="text-slate-700 dark:text-slate-300 mb-1">{dryRunResult.simulated_impact}</p>
          <ul className="list-disc list-inside space-y-0.5 text-slate-600 dark:text-slate-400">
            {dryRunResult.predicted_changes.map((change, i) => (
              <li key={i}>{change}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 拒绝理由输入框 */}
      {showRejectInput && (
        <div className="mb-3 space-y-1.5">
          <input
            type="text"
            placeholder="可选：输入拒绝理由..."
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            className="w-full text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-200 focus:outline-none"
          />
        </div>
      )}

      {/* 底部操作工具栏 */}
      <div className="flex items-center justify-between gap-2 pt-2 border-t border-black/5 dark:border-white/5">
        <div className="flex items-center gap-2">
          {evaluation.supports_dry_run && onSimulateDryRun && (
            <button
              type="button"
              disabled={isSimulating || isSubmitting}
              onClick={handleTriggerDryRun}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
            >
              {isSimulating ? <RotateCcw className="w-3 h-3 animate-spin" /> : <Eye className="w-3 h-3" />}
              Dry-Run 预演
            </button>
          )}
          {evaluation.confirmation_token && (
            <span className="text-[10px] font-mono text-slate-400 dark:text-slate-500 hidden sm:inline">
              Token: {evaluation.confirmation_token.slice(0, 10)}...
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {isHighRisk && (
            <>
              {!showRejectInput ? (
                <button
                  type="button"
                  disabled={isSubmitting}
                  onClick={() => setShowRejectInput(true)}
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium text-red-600 dark:text-red-400 border border-red-300 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-950/40 disabled:opacity-50"
                >
                  <X className="w-3 h-3" />
                  终止打回
                </button>
              ) : (
                <button
                  type="button"
                  disabled={isSubmitting}
                  onClick={handleRejectAction}
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
                >
                  <X className="w-3 h-3" />
                  确认打回
                </button>
              )}

              <button
                type="button"
                disabled={isSubmitting}
                onClick={handleConfirmAction}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-600 text-white hover:bg-red-700 shadow-sm disabled:opacity-50"
              >
                {isSubmitting ? <RotateCcw className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                {isEditing ? '修改参数并执行' : '授权并执行'}
              </button>
            </>
          )}

          {isWrite && (
            <button
              type="button"
              disabled={isSubmitting}
              onClick={handleConfirmAction}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-600 text-white hover:bg-amber-700 shadow-sm disabled:opacity-50"
            >
              {isSubmitting ? <RotateCcw className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
              继续执行
            </button>
          )}

          {isRead && (
            <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
              <Check className="w-3.5 h-3.5" />
              已放行
            </span>
          )}
        </div>
      </div>
    </article>
  );
};
