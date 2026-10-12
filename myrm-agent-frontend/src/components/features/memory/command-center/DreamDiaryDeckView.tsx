'use client';

/**
 * [INPUT]
 * @/services/memory/revocableProvenance::DreamDiaryEntryDTO, RecordDreamDiaryRequestDTO
 *
 * [OUTPUT]
 * DreamDiaryDeckView: Subview component rendering background dreaming consolidation diary logs,
 * scanned turn metrics, promoted memory counters, and trigger consolidation form.
 *
 * [POS]
 * Subcomponent for Item 91 (Revocable Provenance-Qualified Memory and Dream Diary Suite).
 * Strict typing applied: No `any` types allowed. Single responsibility maintained.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Moon, Clock, Scissors, Award, Plus, Sparkles } from 'lucide-react';
import type {
  DreamDiaryEntryDTO,
  RecordDreamDiaryRequestDTO,
} from '@/services/memory/revocableProvenance';

interface DreamDiaryDeckViewProps {
  diaries: DreamDiaryEntryDTO[];
  onRecordDiary: (request: RecordDreamDiaryRequestDTO) => Promise<void>;
}

export function DreamDiaryDeckView({
  diaries,
  onRecordDiary,
}: DreamDiaryDeckViewProps): React.JSX.Element {
  const [showTriggerForm, setShowTriggerForm] = useState<boolean>(false);
  const [agentId, setAgentId] = useState<string>('agent-primary');
  const [scannedTurns, setScannedTurns] = useState<number>(12);
  const [prunedCount, setPrunedCount] = useState<number>(3);
  const [notes, setNotes] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const handleTriggerSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await onRecordDiary({
        agent_id: agentId.trim(),
        scanned_turns: scannedTurns,
        promoted_memory_ids: [`mem_dream_${Date.now().toString().slice(-4)}`],
        pruned_duplicates_count: prunedCount,
        duration_ms: 320.5,
        status: 'completed',
        notes: notes.trim() || '后台梦境离线蒸馏周期完成，已清理冗余并提升高阶经验。',
      });
      setNotes('');
      setShowTriggerForm(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="dream-diary-deck-view">
      {/* Header and Trigger Toggle */}
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          共 {diaries.length} 次离线梦境提炼周期（对标 OpenClaw 梦境日记，透明展现后台反思与剪枝）
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setShowTriggerForm(!showTriggerForm)}
          className="flex items-center gap-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <Moon className="w-3.5 h-3.5 text-indigo-400" />
          {showTriggerForm ? '收起表单' : '记录梦境提炼'}
        </Button>
      </div>

      {/* Trigger Form */}
      {showTriggerForm && (
        <form
          onSubmit={handleTriggerSubmit}
          className="rounded-lg border border-indigo-500/30 bg-indigo-500/5 p-3 space-y-2 text-xs"
          data-testid="record-dream-diary-form"
        >
          <div className="font-medium text-foreground flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            记录后台梦境蒸馏周期 (Dream Consolidation)
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label htmlFor="dream-agent-id" className="block text-muted-foreground mb-1">
                目标 Agent ID
              </label>
              <input
                id="dream-agent-id"
                type="text"
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                required
              />
            </div>
            <div>
              <label htmlFor="dream-scanned-turns" className="block text-muted-foreground mb-1">
                扫描对话轮数
              </label>
              <input
                id="dream-scanned-turns"
                type="number"
                min="1"
                value={scannedTurns}
                onChange={(e) => setScannedTurns(Number(e.target.value))}
                className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                required
              />
            </div>
            <div>
              <label htmlFor="dream-pruned-count" className="block text-muted-foreground mb-1">
                剪枝去重数量
              </label>
              <input
                id="dream-pruned-count"
                type="number"
                min="0"
                value={prunedCount}
                onChange={(e) => setPrunedCount(Number(e.target.value))}
                className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                required
              />
            </div>
          </div>
          <div>
            <label htmlFor="dream-notes" className="block text-muted-foreground mb-1">
              蒸馏提炼总结 / 梦境心得
            </label>
            <input
              id="dream-notes"
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="例如：提炼了 1 条测试驱动开发决策，剔除了 3 处关于临时日志格式的重复约束。"
              className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          <div className="flex justify-end pt-1">
            <Button
              type="submit"
              size="sm"
              disabled={isSubmitting}
              className="text-xs bg-indigo-600 hover:bg-indigo-700 text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <Plus className="w-3.5 h-3.5 mr-1" />
              {isSubmitting ? '记录中...' : '提交梦境日记'}
            </Button>
          </div>
        </form>
      )}

      {/* Dream Diary Timeline Cards */}
      <div className="space-y-2.5 max-h-96 overflow-y-auto pr-1">
        {diaries.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border/70 p-6 text-center text-xs text-muted-foreground">
            暂无梦境整合日记记录
          </div>
        ) : (
          diaries.map((diary) => (
            <div
              key={diary.dream_id}
              className="rounded-lg border border-border/60 bg-accent/20 p-3 space-y-2 text-xs transition-colors hover:bg-accent/30"
              data-testid={`dream-diary-card-${diary.dream_id}`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Moon className="w-4 h-4 text-indigo-400" />
                  <span className="font-semibold text-foreground">{diary.dream_id}</span>
                  <Badge variant="outline" className="text-[10px] bg-indigo-500/10 text-indigo-400 border-indigo-500/30">
                    {diary.agent_id}
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  <Badge
                    variant={diary.status === 'completed' ? 'default' : 'secondary'}
                    className="text-[10px]"
                  >
                    {diary.status}
                  </Badge>
                  <span className="text-[11px] text-muted-foreground flex items-center gap-0.5">
                    <Clock className="w-3 h-3" />
                    {diary.duration_ms.toFixed(1)}ms
                  </span>
                </div>
              </div>

              {/* Metrics row */}
              <div className="grid grid-cols-3 gap-2 rounded bg-background/50 p-2 text-[11px]">
                <div className="flex items-center gap-1.5">
                  <span className="text-muted-foreground">扫描轮次:</span>
                  <span className="font-semibold text-foreground">{diary.scanned_turns} turns</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Award className="w-3 h-3 text-emerald-500" />
                  <span className="text-muted-foreground">晋升事实:</span>
                  <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                    {diary.promoted_memory_ids.length} 项
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Scissors className="w-3 h-3 text-amber-500" />
                  <span className="text-muted-foreground">剪枝去重:</span>
                  <span className="font-semibold text-amber-600 dark:text-amber-400">
                    {diary.pruned_duplicates_count} 条
                  </span>
                </div>
              </div>

              {/* Notes */}
              {diary.notes && (
                <div className="text-[11px] text-muted-foreground italic bg-accent/30 p-2 rounded border border-border/30">
                  {diary.notes}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
