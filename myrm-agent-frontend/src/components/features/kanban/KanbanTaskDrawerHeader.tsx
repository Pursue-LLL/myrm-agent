'use client';

import { cn } from '@/lib/utils/classnameUtils';
import type { KanbanTask, TaskStatus, PromoteResult } from '@/services/kanban';
import { NEXT_STATUSES, STATUS_DOT } from './kanban-styles';
import type { Agent } from '@/services/agent';

interface StatusActionsBarProps {
  task: KanbanTask;
  promoting: boolean;
  showReclaimDialog: boolean;
  setShowReclaimDialog: (v: boolean) => void;
  reclaimReason: string;
  setReclaimReason: (v: string) => void;
  reclaimAgentId: string;
  setReclaimAgentId: (v: string) => void;
  reclaiming: boolean;
  agents: Agent[];
  promoteConfirm: PromoteResult | null;
  setPromoteConfirm: (v: PromoteResult | null) => void;
  handleMove: (status: TaskStatus) => void;
  handleReclaim: () => void;
  handleForcePromote: () => void;
  t: (key: string) => string;
}

export function StatusActionsBar({
  task,
  promoting,
  showReclaimDialog,
  setShowReclaimDialog,
  reclaimReason,
  setReclaimReason,
  reclaimAgentId,
  setReclaimAgentId,
  reclaiming,
  agents,
  promoteConfirm,
  setPromoteConfirm,
  handleMove,
  handleReclaim,
  handleForcePromote,
  t,
}: StatusActionsBarProps) {
  const nextStatuses = NEXT_STATUSES[task.status] ?? [];

  return (
    <>
      {(nextStatuses.length > 0 || task.status === 'running') && (
        <div className="flex gap-1.5 mt-2 flex-wrap">
          {nextStatuses.map((ns) => (
            <button
              key={ns}
              onClick={() => handleMove(ns)}
              disabled={promoting}
              className="text-[10px] px-2 py-1 rounded-full bg-muted hover:bg-muted-foreground/20 transition-colors font-medium disabled:opacity-50"
            >
              {t(`moveTo.${ns}`)}
            </button>
          ))}
          {task.status === 'running' && (
            <button
              onClick={() => setShowReclaimDialog(true)}
              className="text-[10px] px-2 py-1 rounded-full bg-destructive/10 hover:bg-destructive/20 text-destructive font-medium transition-colors"
            >
              {t('reclaimConfirm')}
            </button>
          )}
        </div>
      )}

      {showReclaimDialog && (
        <div className="mt-2 p-2.5 rounded-lg border border-destructive/30 bg-destructive/5 space-y-2">
          <p className="text-[11px] font-medium text-destructive">{t('reclaimTitle')}</p>
          <p className="text-[10px] text-muted-foreground">{t('reclaimDesc')}</p>
          <input
            type="text"
            value={reclaimReason}
            onChange={(e) => setReclaimReason(e.target.value)}
            placeholder={t('reclaimReasonPlaceholder')}
            className="w-full text-[10px] px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-destructive/50"
          />
          {agents.length > 0 && (
            <div className="space-y-1">
              <label className="text-[10px] text-muted-foreground">{t('reclaimReassignLabel')}</label>
              <select
                value={reclaimAgentId}
                onChange={(e) => setReclaimAgentId(e.target.value)}
                className="w-full text-[10px] px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-destructive/50"
              >
                <option value="">—</option>
                {agents.map((ag) => (
                  <option key={ag.id} value={ag.id}>
                    {ag.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="flex gap-2 pt-1">
            <button
              onClick={handleReclaim}
              disabled={reclaiming}
              className="text-[10px] px-2.5 py-1 rounded-full bg-destructive/20 hover:bg-destructive/30 text-destructive font-medium disabled:opacity-50"
            >
              {t('reclaimConfirm')}
            </button>
            <button
              onClick={() => {
                setShowReclaimDialog(false);
                setReclaimReason('');
                setReclaimAgentId('');
              }}
              className="text-[10px] px-2.5 py-1 rounded-full bg-muted hover:bg-muted-foreground/20 font-medium"
            >
              {t('cancel')}
            </button>
          </div>
        </div>
      )}

      {promoteConfirm && (
        <div className="mt-2 p-2.5 rounded-lg border border-chart-5/30 bg-chart-5/5 space-y-2">
          <p className="text-[11px] font-medium text-chart-5">{t('promoteUnmetDeps')}</p>
          <ul className="space-y-1">
            {promoteConfirm.unmet_parents.map((p) => (
              <li key={p.task_id} className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                <span className={cn('w-1.5 h-1.5 rounded-full', STATUS_DOT[p.status] ?? 'bg-muted-foreground/30')} />
                <span className="truncate">{p.title}</span>
                <span className="text-[9px] opacity-60">({p.status})</span>
              </li>
            ))}
          </ul>
          <div className="flex gap-2 pt-1">
            <button
              onClick={handleForcePromote}
              disabled={promoting}
              className="text-[10px] px-2.5 py-1 rounded-full bg-chart-5/20 hover:bg-chart-5/30 text-chart-5 font-medium disabled:opacity-50"
            >
              {t('promoteForce')}
            </button>
            <button
              onClick={() => setPromoteConfirm(null)}
              className="text-[10px] px-2.5 py-1 rounded-full bg-muted hover:bg-muted-foreground/20 font-medium"
            >
              {t('cancel')}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
