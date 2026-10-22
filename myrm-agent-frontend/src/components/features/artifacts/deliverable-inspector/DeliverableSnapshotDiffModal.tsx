/**
 * [INPUT] snapshots, currentVersion, diffItems, onRollback, onClose, isOpen
 * [OUTPUT] DeliverableSnapshotDiffModal component rendering snapshot timeline and diff with rollback
 * [POS] artifacts/deliverable-inspector/DeliverableSnapshotDiffModal.tsx
 */

'use client';

import React, { useState, useEffect } from 'react';
import {
  History,
  RotateCcw,
  GitCompare,
  X,
  FileDiff,
  Sparkles,
  ArrowRight,
} from 'lucide-react';
import type {
  DeliverableSnapshot,
  SnapshotDiffItem,
  DiffChangeStatus,
} from './deliverableInspectorTypes';

export interface DeliverableSnapshotDiffModalProps {
  isOpen: boolean;
  snapshots: DeliverableSnapshot[];
  currentVersion: number;
  diffItems: SnapshotDiffItem[];
  onRollback: (targetVersion: number) => void;
  onClose: () => void;
}

const STATUS_BADGE_MAP: Record<DiffChangeStatus, { label: string; badgeClass: string }> = {
  modified: {
    label: '局部修改',
    badgeClass: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30',
  },
  added: {
    label: '新增节点',
    badgeClass: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
  },
  removed: {
    label: '移除节点',
    badgeClass: 'bg-destructive/10 text-destructive border-destructive/30',
  },
  unchanged: {
    label: '原样保留',
    badgeClass: 'bg-muted text-muted-foreground border-border/40',
  },
};

export const DeliverableSnapshotDiffModal: React.FC<DeliverableSnapshotDiffModalProps> = ({
  isOpen,
  snapshots,
  currentVersion,
  diffItems,
  onRollback,
  onClose,
}) => {
  const [selectedVersion, setSelectedVersion] = useState<number>(currentVersion);

  useEffect(() => {
    setSelectedVersion(currentVersion);
  }, [currentVersion, isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  const isCurrentVersion = selectedVersion === currentVersion;

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="snapshot-diff-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto m-0 h-full w-full max-w-none max-h-none border-0 animate-in fade-in duration-150"
    >
      <div className="w-full max-w-3xl rounded-xl border border-border/80 bg-card text-card-foreground shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-5 py-3.5 bg-muted/20">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary border border-primary/20">
              <History className="h-4 w-4" />
            </div>
            <div>
              <h3
                id="snapshot-diff-modal-title"
                className="text-sm font-semibold text-foreground tracking-tight"
              >
                版本快照对比与安全回退
              </h3>
              <p className="text-[11px] text-muted-foreground">
                可核验的局部修改历史 · 随时一键无损撤销
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            aria-label="关闭快照对比"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body (Version Timeline + Diff Cards) */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 text-xs">
          {/* Version chips */}
          <div className="space-y-1.5">
            <span className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
              <GitCompare className="h-3 w-3" />
              快照版本分支：
            </span>
            <div className="flex flex-wrap gap-2">
              {snapshots.map((snap) => {
                const isSelected = snap.version === selectedVersion;
                const isCurrent = snap.version === currentVersion;
                return (
                  <button
                    key={snap.version}
                    type="button"
                    onClick={() => {
                      setSelectedVersion(snap.version);
                    }}
                    className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-all flex items-center gap-1.5 ${
                      isSelected
                        ? 'border-primary bg-primary/10 text-primary shadow-xs'
                        : 'border-border/60 bg-muted/30 text-muted-foreground hover:bg-muted'
                    }`}
                  >
                    <span>v{snap.version}</span>
                    {isCurrent && (
                      <span className="rounded bg-primary/20 text-primary px-1 py-0.2 text-[10px]">
                        当前
                      </span>
                    )}
                    {snap.changeDescription && (
                      <span className="text-[11px] opacity-75 truncate max-w-[120px]">
                        · {snap.changeDescription}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Diffs List */}
          <div className="space-y-2 pt-2">
            <span className="text-[11px] font-medium text-foreground flex items-center gap-1.5">
              <FileDiff className="h-3.5 w-3.5 text-primary" />
              节点变更对比明细 ({diffItems.length} 个节点)
            </span>

            <div className="space-y-2 max-h-[42vh] overflow-y-auto pr-1">
              {diffItems.map((item) => {
                const statusMeta = STATUS_BADGE_MAP[item.status];
                const isModified = item.status === 'modified';

                return (
                  <div
                    key={item.nodeId}
                    className="rounded-lg border border-border/60 bg-card p-3 space-y-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground text-xs">
                        {item.nodeTitle}
                      </span>
                      <span
                        className={`rounded border px-2 py-0.5 text-[10px] font-medium ${statusMeta.badgeClass}`}
                      >
                        {statusMeta.label}
                      </span>
                    </div>

                    {isModified && item.beforeContent && item.afterContent && (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] pt-1">
                        <div className="rounded border border-destructive/20 bg-destructive/5 p-2 space-y-1">
                          <span className="font-mono text-destructive text-[10px] block">
                            修改前：
                          </span>
                          <p className="line-clamp-3 text-muted-foreground font-mono text-[10px] whitespace-pre-wrap">
                            {item.beforeContent}
                          </p>
                        </div>
                        <div className="rounded border border-emerald-500/20 bg-emerald-500/5 p-2 space-y-1">
                          <span className="font-mono text-emerald-600 dark:text-emerald-400 text-[10px] block">
                            修改后（当前）：
                          </span>
                          <p className="line-clamp-3 text-foreground font-mono text-[10px] whitespace-pre-wrap">
                            {item.afterContent}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Footer with Rollback action */}
        <div className="flex items-center justify-between border-t px-5 py-3 bg-muted/20">
          <div className="text-[11px] text-muted-foreground">
            {isCurrentVersion ? (
              <span>当前正在查看最新版本</span>
            ) : (
              <span>选定回退到 v{selectedVersion}，其他页面完好保留</span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              关闭
            </button>
            {!isCurrentVersion && (
              <button
                type="button"
                onClick={() => {
                  onRollback(selectedVersion);
                  onClose();
                }}
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary hover:bg-primary/90 px-3.5 py-1.5 text-xs font-semibold text-primary-foreground shadow-xs transition-colors"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                <span>无损回退到 v{selectedVersion}</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </dialog>
  );
};
