'use client';

/**
 * [INPUT]
 * @/services/memory/privateNotebook::switchToNewContext, NewContextResponseDTO
 *
 * [OUTPUT]
 * PrivateNotebookHandoverView: Subcomponent for clean context window handover and notes carry-over.
 *
 * [POS]
 * Subcomponent for Item 89 (Transparent Inspectable Model Private Notebook Suite).
 * Strict typing applied: No `any` types allowed.
 */

import React, { useState } from 'react';
import { Button } from '@/components/primitives/button';
import { ArrowRightLeft, CheckCircle2 } from 'lucide-react';
import {
  switchToNewContext,
  type NewContextResponseDTO,
} from '@/services/memory/privateNotebook';

interface PrivateNotebookHandoverViewProps {
  onHandoverSuccess: (result: NewContextResponseDTO) => void;
  onError: (errorMsg: string) => void;
}

export function PrivateNotebookHandoverView({
  onHandoverSuccess,
  onError,
}: PrivateNotebookHandoverViewProps): React.JSX.Element {
  const [handoverReason, setHandoverReason] = useState<string>('');
  const [handoverResult, setHandoverResult] = useState<NewContextResponseDTO | null>(null);
  const [isExecutingHandover, setIsExecutingHandover] = useState<boolean>(false);

  const handleExecuteHandover = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!handoverReason.trim()) return;
    setIsExecutingHandover(true);
    try {
      const res = await switchToNewContext({
        summary_reason: handoverReason.trim(),
      });
      setHandoverResult(res);
      onHandoverSuccess(res);
    } catch {
      onError('跨窗口接力移交失败');
    } finally {
      setIsExecutingHandover(false);
    }
  };

  return (
    <form
      onSubmit={handleExecuteHandover}
      className="space-y-3 rounded-md border border-border/70 p-3 bg-card"
      data-testid="handover-form"
    >
      <div className="space-y-1">
        <label htmlFor="handover-reason-input" className="text-xs font-semibold text-foreground">
          跨窗口交接说明与状态摘要 (summary_reason):
        </label>
        <textarea
          id="handover-reason-input"
          placeholder="例如: 阶段一框架层与服务层已验证通过，清理长程执行冗余历史，保留本地 .myrm/agent_notes/ 架构笔记无损接力..."
          value={handoverReason}
          onChange={(e) => setHandoverReason(e.target.value)}
          rows={3}
          className="w-full rounded border border-input bg-background p-2 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          data-testid="handover-reason-textarea"
        />
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="text-[11px] text-muted-foreground">
          调用 new_context 后：主上下文重置为 0 Token，全部透明笔记物理保留，沙箱状态完整维持。
        </div>
        <Button
          type="submit"
          size="sm"
          disabled={isExecutingHandover || !handoverReason.trim()}
          className="gap-1.5 shrink-0"
          data-testid="execute-handover-btn"
        >
          <ArrowRightLeft className="h-3.5 w-3.5" />
          {isExecutingHandover ? '轮转移交中...' : '启动新上下文接力'}
        </Button>
      </div>

      {handoverResult && (
        <div
          className="rounded border border-green-500/30 p-2.5 bg-green-500/10 space-y-1 text-xs text-foreground"
          data-testid="handover-result-box"
        >
          <div className="font-semibold text-green-600 dark:text-green-400 flex items-center gap-1">
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span>接力移交成功</span>
          </div>
          <div>
            新上下文标识: <span className="font-mono font-bold">{handoverResult.new_context_id}</span>
          </div>
          <div>
            前置归档上下文: <span className="font-mono">{handoverResult.previous_context_id}</span>
          </div>
          <div>
            成功无损继承笔记: <span className="font-bold">{handoverResult.carried_notes_count}</span> 篇
          </div>
        </div>
      )}
    </form>
  );
}
