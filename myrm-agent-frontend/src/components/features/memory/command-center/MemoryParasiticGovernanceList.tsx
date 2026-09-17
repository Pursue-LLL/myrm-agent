'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::MemoryCommandParasiticMemory (POS: 寄生沉睡记忆契约)
 *
 * [OUTPUT]
 * MemoryParasiticGovernanceList: 低效沉睡记忆治理列表与批量归档确认操作。
 *
 * [POS]
 * 沉睡记忆治理池视图组件。呈现未产生引用的记忆列表，支持单条与一键批量归档。
 */

import React from 'react';
import { AlertTriangle, Archive, Check, CheckCircle2, X } from 'lucide-react';

import type { MemoryCommandParasiticMemory } from '@/services/memory/commandCenter';

interface MemoryParasiticGovernanceListProps {
  parasitic: MemoryCommandParasiticMemory[];
  archivingId: string | null;
  archivingAll: boolean;
  confirmArchiveAll: boolean;
  onSetConfirmArchiveAll: (val: boolean) => void;
  onArchive: (item: MemoryCommandParasiticMemory) => Promise<void>;
  onArchiveAll: (items: MemoryCommandParasiticMemory[]) => Promise<void>;
}

export const MemoryParasiticGovernanceList: React.FC<MemoryParasiticGovernanceListProps> = ({
  parasitic,
  archivingId,
  archivingAll,
  confirmArchiveAll,
  onSetConfirmArchiveAll,
  onArchive,
  onArchiveAll,
}) => {
  return (
    <div className="lg:col-span-5 flex flex-col gap-3 p-4 rounded-xl border border-border/40 bg-background/40">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-500" />
          <h4 className="text-xs sm:text-sm font-semibold text-foreground">
            低效沉睡记忆治理池
          </h4>
        </div>
        {parasitic.length > 0 ? (
          confirmArchiveAll ? (
            <div className="flex items-center gap-1.5 animate-in fade-in zoom-in-95 duration-150">
              <span className="text-[11px] text-destructive font-medium hidden sm:inline">
                确认全部归档?
              </span>
              <button
                onClick={() => onArchiveAll(parasitic)}
                disabled={archivingAll || archivingId !== null}
                className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-md bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-all shadow-sm active:scale-95 disabled:opacity-50"
              >
                <Check className="w-3 h-3" />
                确认
              </button>
              <button
                onClick={() => onSetConfirmArchiveAll(false)}
                disabled={archivingAll}
                className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-md bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-all active:scale-95"
              >
                <X className="w-3 h-3" />
                取消
              </button>
            </div>
          ) : (
            <button
              onClick={() => onSetConfirmArchiveAll(true)}
              disabled={archivingAll || archivingId !== null}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/25 transition-all shadow-sm active:scale-95 disabled:opacity-50"
            >
              <Archive className="w-3 h-3" />
              {archivingAll ? '批量归档中...' : `一键归档全部 (${parasitic.length})`}
            </button>
          )
        ) : (
          <span className="text-[11px] text-muted-foreground">0 条待处置</span>
        )}
      </div>

      {parasitic.length === 0 ? (
        <div className="py-8 text-center text-xs text-muted-foreground flex flex-col items-center gap-1.5">
          <CheckCircle2 className="w-5 h-5 text-emerald-500" />
          <span>当前记忆库极具活力，未检出低效沉睡记忆。</span>
        </div>
      ) : (
        <div className="flex flex-col gap-2 max-h-[260px] overflow-y-auto pr-1">
          {parasitic.map((item) => (
            <div
              key={item.memory_id}
              className="p-2.5 rounded-lg border border-border/30 bg-card/40 flex flex-col gap-1.5 text-xs"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                  <span className="shrink-0 px-1.5 py-0.5 text-[10px] font-medium rounded bg-muted/80 text-muted-foreground border border-border/40">
                    {item.memory_type === 'episodic'
                      ? '情境'
                      : item.memory_type === 'procedural'
                        ? '流程'
                        : '语义'}
                  </span>
                  <span
                    className="font-medium text-foreground truncate"
                    title={item.content_preview}
                  >
                    {item.content_preview}
                  </span>
                </div>
                <button
                  onClick={() => onArchive(item)}
                  disabled={archivingId === item.memory_id}
                  className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium rounded border border-border hover:bg-muted text-foreground transition-colors shrink-0"
                >
                  <Archive className="w-3 h-3 text-muted-foreground" />
                  {archivingId === item.memory_id ? '归档中...' : '一键归档'}
                </button>
              </div>
              <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                <span>装载 {item.injected_turns_count} 轮 · 引用 0 次</span>
                <span className="text-rose-500 font-medium">浪费 ~{item.wasted_tokens_estimated} T</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
