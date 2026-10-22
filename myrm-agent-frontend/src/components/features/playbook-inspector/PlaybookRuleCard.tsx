/**
 * [INPUT]
 * - ./playbookInspectorTypes::PlaybookRule, PlaybookStatus
 * - lucide-react::Pin, Sparkles, CheckCircle2, AlertTriangle, Archive, ChevronDown, ChevronRight, Edit3, Trash2
 *
 * [OUTPUT]
 * - PlaybookRuleCard: 单条行为规约生命周期卡片组件
 *
 * [POS]
 * 在判断力治理看板中展示单条规约的胜率、触发频次、失败回溯及一键复活/锁定操作。
 */

'use client';

import React, { useState, useCallback } from 'react';
import {
  Pin,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  Archive,
  ChevronDown,
  ChevronRight,
  Edit3,
  Trash2,
} from 'lucide-react';
import type { PlaybookRule, PlaybookStatus } from './playbookInspectorTypes';

export interface PlaybookRuleCardProps {
  rule: PlaybookRule;
  onRevive: () => void;
  onTogglePin: () => void;
  onRetire: () => void;
  onEdit: (updates: Partial<Pick<PlaybookRule, 'title' | 'triggerCondition' | 'directive'>>) => void;
  className?: string;
}

function getStatusBadge(status: PlaybookStatus): { label: string; className: string } {
  switch (status) {
    case 'active':
      return { label: '生效中', className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20' };
    case 'degraded':
      return { label: '降权观察', className: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20' };
    case 'retired':
    default:
      return { label: '已退役', className: 'bg-muted text-muted-foreground border-border/40' };
  }
}

export const PlaybookRuleCard: React.FC<PlaybookRuleCardProps> = ({
  rule,
  onRevive,
  onTogglePin,
  onRetire,
  onEdit,
  className = '',
}) => {
  const [showFailures, setShowFailures] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(rule.title);
  const [editDirective, setEditDirective] = useState(rule.directive);

  const statusBadge = getStatusBadge(rule.status);
  const winRatePercent = Math.round(rule.winRate * 100);

  const handleSaveEdit = useCallback(() => {
    onEdit({
      title: editTitle.trim(),
      directive: editDirective.trim(),
    });
    setIsEditing(false);
  }, [editTitle, editDirective, onEdit]);

  return (
    <article
      aria-label={`规约卡片 - ${rule.title}`}
      className={`rounded-xl border p-4 text-xs transition-all shadow-xs ${
        rule.status === 'active'
          ? 'bg-card/80 border-border/80'
          : rule.status === 'degraded'
          ? 'bg-amber-500/5 border-amber-500/30'
          : 'bg-muted/20 border-border/40 opacity-75'
      } ${className}`}
    >
      <header className="flex items-start justify-between gap-2 mb-2.5">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span
              className={`px-2 py-0.5 rounded-full border text-[10px] font-medium ${statusBadge.className}`}
            >
              {statusBadge.label}
            </span>
            {rule.isPinned && (
              <span className="flex items-center gap-0.5 px-1.5 py-0.2 rounded bg-primary/10 text-primary text-[10px] font-medium border border-primary/20">
                <Pin className="w-2.5 h-2.5 fill-current" aria-hidden="true" />
                <span>置顶锁定</span>
              </span>
            )}
            <span className="text-[10px] text-muted-foreground font-mono">
              触发 {rule.triggerCount} 次 · 胜率 {winRatePercent}%
            </span>
          </div>

          {isEditing ? (
            <input
              type="text"
              value={editTitle}
              onChange={(e) => {
                setEditTitle(e.target.value);
              }}
              className="w-full rounded border border-primary px-2 py-1 text-xs font-semibold text-foreground bg-background"
              aria-label="编辑规约标题"
            />
          ) : (
            <h4 className="text-sm font-semibold text-foreground leading-snug">
              {rule.title}
            </h4>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={onTogglePin}
            className={`p-1.5 rounded transition-colors ${
              rule.isPinned
                ? 'text-primary bg-primary/10'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
            aria-label={rule.isPinned ? '取消置顶锁定' : '置顶锁定防止自动退役'}
            title={rule.isPinned ? '已锁定免退役' : '锁定规约'}
          >
            <Pin className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => {
              setIsEditing((prev) => !prev);
            }}
            className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label="编辑规约内容"
          >
            <Edit3 className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
        </div>
      </header>

      <div className="space-y-2 mb-3">
        <div className="p-2 rounded bg-muted/40 border border-border/30 text-[11px]">
          <span className="text-muted-foreground font-medium">触发条件：</span>
          <span className="text-foreground/90 font-mono ml-1">{rule.triggerCondition}</span>
        </div>

        {isEditing ? (
          <textarea
            value={editDirective}
            onChange={(e) => {
              setEditDirective(e.target.value);
            }}
            rows={3}
            className="w-full rounded border border-primary p-2 text-xs font-sans text-foreground bg-background"
            aria-label="编辑规约动作指令"
          />
        ) : (
          <p className="text-xs text-foreground/90 leading-relaxed bg-background/60 p-2.5 rounded-lg border border-border/40">
            {rule.directive}
          </p>
        )}

        {isEditing && (
          <div className="flex justify-end gap-1.5 pt-1">
            <button
              type="button"
              onClick={() => {
                setIsEditing(false);
              }}
              className="px-2.5 py-1 rounded text-xs text-muted-foreground hover:bg-muted"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleSaveEdit}
              className="px-2.5 py-1 rounded bg-primary text-primary-foreground text-xs font-medium"
            >
              保存
            </button>
          </div>
        )}
      </div>

      <div className="space-y-1.5 mb-3">
        <div className="flex items-center justify-between text-[10px] text-muted-foreground">
          <span>胜率追踪</span>
          <span className="font-mono font-medium">{rule.successCount} 胜 / {rule.triggerCount - rule.successCount} 负</span>
        </div>
        <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden flex">
          <div
            className={`h-full transition-all ${
              winRatePercent >= 80
                ? 'bg-emerald-500'
                : winRatePercent >= 50
                ? 'bg-amber-500'
                : 'bg-rose-500'
            }`}
            style={{ width: `${winRatePercent}%` }}
          />
        </div>
      </div>

      {rule.recentFailures.length > 0 && (
        <div className="mb-3 pt-2 border-t border-border/30">
          <button
            type="button"
            onClick={() => {
              setShowFailures((prev) => !prev);
            }}
            className="flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400 hover:underline"
            aria-expanded={showFailures}
          >
            {showFailures ? (
              <ChevronDown className="w-3 h-3" aria-hidden="true" />
            ) : (
              <ChevronRight className="w-3 h-3" aria-hidden="true" />
            )}
            <span>最近失败会话追溯 ({rule.recentFailures.length})</span>
          </button>

          {showFailures && (
            <div className="mt-2 space-y-1.5 pl-2 border-l-2 border-amber-500/30">
              {rule.recentFailures.map((fail, idx) => (
                <div key={`${fail.sessionId}-${idx}`} className="text-[11px] font-mono bg-muted/60 p-2 rounded">
                  <div className="flex items-center justify-between text-muted-foreground text-[10px] mb-1">
                    <span>会话: {fail.sessionId}</span>
                    <span>{new Date(fail.timestamp).toLocaleTimeString()}</span>
                  </div>
                  <p className="text-rose-600 dark:text-rose-400 font-sans">{fail.errorSummary}</p>
                  {fail.contextSnippet && (
                    <pre className="mt-1 p-1 bg-black/20 rounded text-[10px] text-muted-foreground overflow-x-auto">
                      {fail.contextSnippet}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <footer className="flex items-center justify-between pt-2 border-t border-border/40 text-[11px]">
        <span className="text-muted-foreground text-[10px]">
          更新于 {new Date(rule.updatedAt).toLocaleDateString()}
        </span>

        <div className="flex items-center gap-1.5">
          {rule.status !== 'active' ? (
            <button
              type="button"
              onClick={onRevive}
              className="flex items-center gap-1 px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium transition-colors shadow-xs"
              aria-label="一键强制复活规约"
            >
              <Sparkles className="w-3 h-3" aria-hidden="true" />
              <span>一键复活</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={onRetire}
              className="flex items-center gap-1 px-2 py-1 rounded text-muted-foreground hover:text-rose-600 hover:bg-rose-500/10 transition-colors"
              aria-label="主动停用规约"
            >
              <Archive className="w-3 h-3" aria-hidden="true" />
              <span>停用</span>
            </button>
          )}
        </div>
      </footer>
    </article>
  );
};
