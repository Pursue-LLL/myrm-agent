// @orphan-ok Task Safety Airbag Capsule badge for autonomous run cards
'use client';

/**
 * Task Safety Airbag Capsule badge for autonomous run cards.
 *
 * [INPUT]
 * - @/services/airbag::getAirbagStatus (POS: 获取气囊当前状态与变更清单接口)
 * - ./TimeTravelRollbackModal::TimeTravelRollbackModal (POS: 时光倒流审查与原子撤销交互弹窗)
 *
 * [OUTPUT]
 * - TaskAirbagCapsule: 呈现长任务挂机安全气囊状态与时光倒流触发入口的胶囊徽章
 *
 * [POS]
 * 前端检查点特性层：长任务卡片安全气囊状态徽章与审查入口。
 */

import React, { useState, useEffect, useCallback } from 'react';
import { ShieldCheck, History, RotateCcw } from 'lucide-react';
import { getAirbagStatus, AirbagStatusResponse } from '@/services/airbag';
import { TimeTravelRollbackModal } from './TimeTravelRollbackModal';

interface TaskAirbagCapsuleProps {
  taskId: string;
  workspacePath?: string;
  className?: string;
}

export const TaskAirbagCapsule: React.FC<TaskAirbagCapsuleProps> = ({ taskId, workspacePath, className = '' }) => {
  const [status, setStatus] = useState<AirbagStatusResponse | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getAirbagStatus(taskId, workspacePath);
      setStatus(res);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, [taskId, workspacePath]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  if (!status) {
    return null;
  }

  return (
    <>
      <div
        data-testid="task-airbag-capsule"
        className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
          status.totalFilesChanged > 0
            ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
            : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
        } ${className}`}
      >
        <div className="flex items-center gap-1">
          <ShieldCheck className="w-3.5 h-3.5 shrink-0" />
          <span className="hidden sm:inline">安全气囊已就绪</span>
        </div>

        {status.totalFilesChanged > 0 && (
          <span className="px-1.5 py-0.5 rounded-full bg-background/60 text-[10px] font-mono border border-current/20">
            {status.totalFilesChanged} 项变更
          </span>
        )}

        <button
          type="button"
          onClick={() => setIsModalOpen(true)}
          disabled={loading}
          className="flex items-center gap-1 hover:underline ml-1 font-semibold text-foreground/80 hover:text-foreground cursor-pointer"
          title="审查挂机任务累积变更或执行一键时光倒流"
        >
          <History className="w-3 h-3" />
          <span>审查/复原</span>
        </button>
      </div>

      {isModalOpen && (
        <TimeTravelRollbackModal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          status={status}
          workspacePath={workspacePath}
          onRollbackSuccess={fetchStatus}
        />
      )}
    </>
  );
};
