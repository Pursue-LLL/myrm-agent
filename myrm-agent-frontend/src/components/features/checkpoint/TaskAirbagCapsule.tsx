'use client';

/**
 * Undo capsule for the file changes an unattended goal run has made.
 *
 * [INPUT]
 * - @/services/airbag::getAirbagStatus (POS: 获取气囊当前状态与变更清单接口)
 * - ./TimeTravelRollbackModal::TimeTravelRollbackModal (POS: 审查并撤销改动的交互弹窗)
 *
 * [OUTPUT]
 * - TaskAirbagCapsule: 显示改动数量并提供审查/撤销入口的胶囊徽章；`refreshKey` 变化时重新读取状态
 *
 * [POS]
 * 前端检查点特性层：长任务卡片的改动撤销入口。
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { ShieldCheck, History } from 'lucide-react';
import { getAirbagStatus, AirbagStatusResponse } from '@/services/airbag';
import { TimeTravelRollbackModal } from './TimeTravelRollbackModal';

interface TaskAirbagCapsuleProps {
  taskId: string;
  workspacePath?: string;
  /** Changes whenever the run may have touched files (goal status, turn count); triggers a refetch. */
  refreshKey?: string | number;
  className?: string;
}

export const TaskAirbagCapsule: React.FC<TaskAirbagCapsuleProps> = ({
  taskId,
  workspacePath,
  refreshKey,
  className = '',
}) => {
  const t = useTranslations('taskAirbag');
  const [status, setStatus] = useState<AirbagStatusResponse | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const latestRequest = useRef(0);

  const fetchStatus = useCallback(async () => {
    const requestId = ++latestRequest.current;
    setLoading(true);
    try {
      const res = await getAirbagStatus(taskId, workspacePath);
      if (requestId === latestRequest.current) {
        setStatus(res);
      }
    } catch {
      // The baseline is armed when the run starts; before that (or once dismissed) there is nothing to show.
      if (requestId === latestRequest.current) {
        setStatus(null);
      }
    } finally {
      if (requestId === latestRequest.current) {
        setLoading(false);
      }
    }
  }, [taskId, workspacePath]);

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus, refreshKey]);

  if (!status) {
    return null;
  }

  return (
    <>
      <div
        data-testid="task-airbag-capsule"
        className={`inline-flex max-w-full items-center gap-2 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
          status.totalFilesChanged > 0
            ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
            : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
        } ${className}`}
      >
        <div className="flex items-center gap-1 min-w-0">
          <ShieldCheck className="w-3.5 h-3.5 shrink-0" />
          <span className="hidden sm:inline truncate">{t('ready')}</span>
        </div>

        {status.totalFilesChanged > 0 && (
          <span className="px-1.5 py-0.5 rounded-full bg-background/60 text-[10px] font-mono border border-current/20 whitespace-nowrap">
            {t('changeCount', { count: status.totalFilesChanged })}
          </span>
        )}

        <button
          type="button"
          onClick={() => setIsModalOpen(true)}
          disabled={loading}
          className="flex items-center gap-1 hover:underline font-semibold text-foreground/80 hover:text-foreground cursor-pointer whitespace-nowrap disabled:cursor-wait"
          title={t('reviewHint')}
        >
          <History className="w-3 h-3 shrink-0" />
          <span>{t('review')}</span>
        </button>
      </div>

      {isModalOpen && (
        <TimeTravelRollbackModal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          status={status}
          workspacePath={workspacePath}
          onResolved={fetchStatus}
        />
      )}
    </>
  );
};
