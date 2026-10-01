'use client';

import React, { useState } from 'react';
import { ShieldCheck, AlertTriangle, RotateCcw, X, FileEdit, FilePlus, FileMinus } from 'lucide-react';
import { AirbagStatusResponse, rollbackAirbag, dismissAirbag } from '@/services/airbag';
import { toast } from '@/hooks/shared/useToast';

interface TimeTravelRollbackModalProps {
  isOpen: boolean;
  onClose: () => void;
  status: AirbagStatusResponse;
  workspacePath?: string;
  onRollbackSuccess?: () => void;
}

export const TimeTravelRollbackModal: React.FC<TimeTravelRollbackModalProps> = ({
  isOpen,
  onClose,
  status,
  workspacePath,
  onRollbackSuccess,
}) => {
  const [isRollingBack, setIsRollingBack] = useState(false);
  const [isDismissing, setIsDismissing] = useState(false);

  if (!isOpen) {
    return null;
  }

  const handleRollback = async () => {
    setIsRollingBack(true);
    try {
      const res = await rollbackAirbag(status.taskId, workspacePath);
      if (res.success && res.status === 'rolled_back') {
        toast({
          title: '时光倒流成功',
          description: '工作区已原子无损回滚至任务起跑点。',
          variant: 'default',
        });
        window.dispatchEvent(new CustomEvent('app_resync_required'));
        if (onRollbackSuccess) {
          onRollbackSuccess();
        }
        onClose();
      } else {
        toast({
          title: '回滚失败',
          description: '无法恢复到起跑快照，请检查工作区文件权限。',
          variant: 'destructive',
        });
      }
    } catch (err) {
      toast({
        title: '回滚请求失败',
        description: err instanceof Error ? err.message : '未知异常',
        variant: 'destructive',
      });
    } finally {
      setIsRollingBack(false);
    }
  };

  const handleDismiss = async () => {
    setIsDismissing(true);
    try {
      const res = await dismissAirbag(status.taskId, workspacePath);
      if (res.success) {
        toast({
          title: '安全气囊已归档',
          description: '变更已确认保留。',
          variant: 'default',
        });
        onClose();
      }
    } catch {
      toast({
        title: '归档失败',
        variant: 'destructive',
      });
    } finally {
      setIsDismissing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <div className="w-full max-w-xl bg-background border border-border rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-muted/30">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-foreground">时光倒流 · 安全气囊审查</h2>
              <p className="text-xs text-muted-foreground">任务起跑基线守护与原子复原</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 overflow-y-auto space-y-4 text-sm">
          {/* External effect warnings if present */}
          {status.externalEffects.length > 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3.5 space-y-1.5">
              <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 font-medium text-xs">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>外部不可逆动作警示（文件回滚无法撤销以下操作）：</span>
              </div>
              <ul className="list-disc list-inside text-xs text-muted-foreground pl-1 space-y-0.5">
                {status.externalEffects.map((fx, idx) => (
                  <li key={`fx-${idx}`}>{fx}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Cumulative Changes Statistics */}
          <div className="grid grid-cols-3 gap-3">
            <div className="p-3 rounded-lg bg-muted/40 border border-border/50 text-center">
              <div className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground mb-1">
                <FileEdit className="w-3.5 h-3.5 text-blue-500" />
                <span>已修改</span>
              </div>
              <div className="text-lg font-semibold text-foreground">{status.modifiedFiles.length}</div>
            </div>
            <div className="p-3 rounded-lg bg-muted/40 border border-border/50 text-center">
              <div className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground mb-1">
                <FilePlus className="w-3.5 h-3.5 text-emerald-500" />
                <span>已新增</span>
              </div>
              <div className="text-lg font-semibold text-foreground">{status.addedFiles.length}</div>
            </div>
            <div className="p-3 rounded-lg bg-muted/40 border border-border/50 text-center">
              <div className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground mb-1">
                <FileMinus className="w-3.5 h-3.5 text-rose-500" />
                <span>已删除</span>
              </div>
              <div className="text-lg font-semibold text-foreground">{status.deletedFiles.length}</div>
            </div>
          </div>

          {/* Mutated File List */}
          <div className="space-y-1.5">
            <div className="text-xs font-medium text-muted-foreground">受影响文件列表（共 {status.totalFilesChanged} 项）：</div>
            <div className="max-h-48 overflow-y-auto rounded-lg border border-border bg-muted/20 p-2 space-y-1 font-mono text-xs">
              {status.modifiedFiles.map((f) => (
                <div key={`m-${f}`} className="flex items-center gap-2 text-foreground/90">
                  <span className="text-blue-500 font-semibold">[M]</span>
                  <span className="truncate">{f}</span>
                </div>
              ))}
              {status.addedFiles.map((f) => (
                <div key={`a-${f}`} className="flex items-center gap-2 text-foreground/90">
                  <span className="text-emerald-500 font-semibold">[A]</span>
                  <span className="truncate">{f}</span>
                </div>
              ))}
              {status.deletedFiles.map((f) => (
                <div key={`d-${f}`} className="flex items-center gap-2 text-foreground/90">
                  <span className="text-rose-500 font-semibold">[D]</span>
                  <span className="truncate">{f}</span>
                </div>
              ))}
              {status.totalFilesChanged === 0 && (
                <div className="text-center py-4 text-muted-foreground font-sans">工作区与起跑原点一致，暂无变动。</div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3.5 border-t border-border bg-muted/20">
          <button
            type="button"
            onClick={handleDismiss}
            disabled={isDismissing || isRollingBack}
            className="px-3.5 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-50"
          >
            {isDismissing ? '归档中...' : '确认成果并归档'}
          </button>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isRollingBack}
              className="px-3.5 py-1.5 rounded-lg border border-transparent text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              稍后处理
            </button>
            <button
              type="button"
              onClick={handleRollback}
              disabled={isRollingBack || !status.canRollback || status.totalFilesChanged === 0}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-medium shadow transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${isRollingBack ? 'animate-spin' : ''}`} />
              <span>{isRollingBack ? '正在时光倒流...' : '时光倒流·完整复原'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
