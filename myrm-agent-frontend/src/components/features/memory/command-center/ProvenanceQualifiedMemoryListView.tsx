'use client';

/**
 * [INPUT]
 * @/services/memory/revocableProvenance::ProvenanceQualifiedMemoryDTO, SaveProvenanceMemoryRequestDTO
 *
 * [OUTPUT]
 * ProvenanceQualifiedMemoryListView: Subview component rendering memories, bidirectional provenance graph details,
 * atomic memory forget (revocation) dialog, and quick memory creation form.
 *
 * [POS]
 * Subcomponent for Item 91 (Revocable Provenance-Qualified Memory and Dream Diary Suite).
 * Strict typing applied: No `any` types allowed. Single responsibility maintained.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Compass, Trash2, CheckCircle2, MessageSquare, Plus, FileText } from 'lucide-react';
import type {
  ProvenanceQualifiedMemoryDTO,
  SaveProvenanceMemoryRequestDTO,
} from '@/services/memory/revocableProvenance';

interface ProvenanceQualifiedMemoryListViewProps {
  memories: ProvenanceQualifiedMemoryDTO[];
  onForgetMemory: (memoryId: string, reason: string) => Promise<void>;
  onSaveMemory: (request: SaveProvenanceMemoryRequestDTO) => Promise<void>;
}

export function ProvenanceQualifiedMemoryListView({
  memories,
  onForgetMemory,
  onSaveMemory,
}: ProvenanceQualifiedMemoryListViewProps): React.JSX.Element {
  const [selectedMemoryId, setSelectedMemoryId] = useState<string | null>(null);
  const [forgetReason, setForgetReason] = useState<string>('');
  const [forgettingId, setForgettingId] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // New Memory form fields
  const [newStatement, setNewStatement] = useState<string>('');
  const [newCategory, setNewCategory] = useState<string>('architecture_pattern');
  const [newSessionId, setNewSessionId] = useState<string>('session_dev_arch');
  const [newMessageId, setNewMessageId] = useState<string>('msg_arch_42');
  const [newQuote, setNewQuote] = useState<string>('');

  const selectedMemory = memories.find((m) => m.memory_id === selectedMemoryId) ?? null;

  const handleForgetSubmit = async (memoryId: string) => {
    setForgettingId(memoryId);
    try {
      await onForgetMemory(memoryId, forgetReason);
      setForgetReason('');
    } finally {
      setForgettingId(null);
    }
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newStatement.trim() || !newQuote.trim()) return;
    setIsSubmitting(true);
    try {
      await onSaveMemory({
        statement: newStatement.trim(),
        category: newCategory,
        session_id: newSessionId.trim(),
        message_id: newMessageId.trim(),
        turn_index: 1,
        quote_snippet: newQuote.trim(),
        confidence_score: 0.95,
      });
      setNewStatement('');
      setNewQuote('');
      setShowAddForm(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="provenance-qualified-memory-list-view">
      {/* Action Bar */}
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          共 {memories.length} 条已溯源长程记忆（支持双向对话回溯与无损定点撤销）
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <Plus className="w-3.5 h-3.5" />
          {showAddForm ? '收起表单' : '录入溯源事实'}
        </Button>
      </div>

      {/* Quick Add Form */}
      {showAddForm && (
        <form
          onSubmit={handleCreateSubmit}
          className="rounded-lg border border-primary/20 bg-primary/5 p-3 space-y-2 text-xs"
          data-testid="add-provenance-memory-form"
        >
          <div className="font-medium text-foreground">快速固化溯源记忆</div>
          <div>
            <label htmlFor="new-statement-input" className="block text-muted-foreground mb-1 font-medium">
              提炼事实 (Statement)
            </label>
            <input
              id="new-statement-input"
              type="text"
              value={newStatement}
              onChange={(e) => setNewStatement(e.target.value)}
              placeholder="例如：核心业务严禁引入 Any 类型，强制全链路强类型检查。"
              className="w-full rounded border border-border bg-background px-2.5 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              required
            />
          </div>
          <div>
            <label htmlFor="new-quote-input" className="block text-muted-foreground mb-1 font-medium">
              原文佐证引文 (Verbatim Quote Snippet)
            </label>
            <input
              id="new-quote-input"
              type="text"
              value={newQuote}
              onChange={(e) => setNewQuote(e.target.value)}
              placeholder="例如：用户在第 4 轮提出：“必须消除所有 any 类型”"
              className="w-full rounded border border-border bg-background px-2.5 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              required
            />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label htmlFor="new-category-input" className="block text-muted-foreground mb-1">
                分类标签
              </label>
              <input
                id="new-category-input"
                type="text"
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
                className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label htmlFor="new-session-input" className="block text-muted-foreground mb-1">
                源 Session ID
              </label>
              <input
                id="new-session-input"
                type="text"
                value={newSessionId}
                onChange={(e) => setNewSessionId(e.target.value)}
                className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label htmlFor="new-msg-input" className="block text-muted-foreground mb-1">
                源 Message ID
              </label>
              <input
                id="new-msg-input"
                type="text"
                value={newMessageId}
                onChange={(e) => setNewMessageId(e.target.value)}
                className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>
          <div className="flex justify-end pt-1">
            <Button
              type="submit"
              size="sm"
              disabled={isSubmitting || !newStatement.trim() || !newQuote.trim()}
              className="text-xs focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {isSubmitting ? '保存中...' : '提交沉淀'}
            </Button>
          </div>
        </form>
      )}

      {/* Main Grid: List + Provenance Inspector */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Left: Memory List */}
        <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
          {memories.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border/70 p-6 text-center text-xs text-muted-foreground">
              暂无已溯源记忆条目
            </div>
          ) : (
            memories.map((mem) => {
              const isSelected = selectedMemoryId === mem.memory_id;
              return (
                <button
                  type="button"
                  key={mem.memory_id}
                  onClick={() => setSelectedMemoryId(mem.memory_id)}
                  className={`w-full text-left rounded-lg border p-3 cursor-pointer transition-colors text-xs focus:outline-none focus:ring-2 focus:ring-primary ${
                    isSelected
                      ? 'border-primary bg-primary/10'
                      : mem.is_revoked
                        ? 'border-destructive/30 bg-destructive/5 opacity-70'
                        : 'border-border/60 bg-accent/20 hover:bg-accent/40'
                  }`}
                  data-testid={`memory-card-${mem.memory_id}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="font-medium text-foreground line-clamp-2">
                      {mem.statement}
                    </div>
                    {mem.is_revoked ? (
                      <Badge variant="destructive" className="shrink-0 text-[10px]">已定点遗忘</Badge>
                    ) : (
                      <Badge variant="outline" className="shrink-0 text-[10px] bg-primary/10 text-primary border-primary/30">
                        {mem.category}
                      </Badge>
                    )}
                  </div>
                  <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
                    <span className="flex items-center gap-1 font-mono">
                      <Compass className="w-3 h-3 text-primary" />
                      {mem.provenance.session_id.slice(0, 16)}
                    </span>
                    <span>置信度: {(mem.provenance.confidence_score * 100).toFixed(0)}%</span>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Right: Provenance Inspector & Atomic Forget */}
        <div className="rounded-lg border border-border/60 bg-accent/15 p-3 space-y-3">
          <div className="flex items-center justify-between border-b border-border/40 pb-2">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <Compass className="w-4 h-4 text-primary" />
              双向溯源图谱与遗忘控制台
            </span>
            {selectedMemory && (
              <span className="font-mono text-[10px] text-muted-foreground">{selectedMemory.memory_id}</span>
            )}
          </div>

          {selectedMemory ? (
            <div className="space-y-3 text-xs" data-testid="provenance-detail-box">
              <div>
                <span className="text-muted-foreground font-medium">沉淀事实陈述：</span>
                <p className="mt-0.5 text-foreground font-medium bg-background/60 p-2 rounded border border-border/40">
                  {selectedMemory.statement}
                </p>
              </div>

              {/* Provenance Origin Metadata */}
              <div className="rounded-md border border-border/50 bg-background/50 p-2.5 space-y-1.5">
                <div className="text-[11px] font-semibold text-primary flex items-center gap-1">
                  <MessageSquare className="w-3.5 h-3.5" />
                  溯源锚点信息 (Provenance Origin)
                </div>
                <div className="grid grid-cols-2 gap-1.5 text-[11px] font-mono">
                  <div>
                    <span className="text-muted-foreground">Session: </span>
                    <span className="text-foreground">{selectedMemory.provenance.session_id}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Message ID: </span>
                    <span className="text-foreground">{selectedMemory.provenance.message_id}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">对话轮次: </span>
                    <span className="text-foreground">Turn #{selectedMemory.provenance.turn_index}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">置信度: </span>
                    <span className="text-foreground">{(selectedMemory.provenance.confidence_score * 100).toFixed(1)}%</span>
                  </div>
                </div>
                <div className="pt-1">
                  <div className="text-[11px] text-muted-foreground flex items-center gap-1 mb-0.5">
                    <FileText className="w-3 h-3" />
                    原始上下文金句 (Verbatim Transcript Quote):
                  </div>
                  <blockquote className="rounded bg-muted/40 p-2 text-foreground italic border-l-2 border-primary/50 text-[11px]">
                    "{selectedMemory.provenance.quote_snippet}"
                  </blockquote>
                </div>
              </div>

              {/* Atomic Forget Section */}
              {selectedMemory.is_revoked ? (
                <div className="rounded border border-destructive/30 bg-destructive/10 p-2 text-[11px] text-destructive">
                  <div className="font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    已执行原子定点遗忘 (Memory Forget)
                  </div>
                  <div className="mt-1 text-muted-foreground">
                    原因: {selectedMemory.revocation_reason || '用户无损剔除'}
                  </div>
                  <div className="text-[10px] text-muted-foreground">
                    底座原始会话记录保持不变，记忆索引已安全排除。
                  </div>
                </div>
              ) : (
                <div className="rounded border border-amber-500/30 bg-amber-500/5 p-2.5 space-y-2">
                  <div className="font-medium text-amber-700 dark:text-amber-300 flex items-center gap-1 text-[11px]">
                    <Trash2 className="w-3.5 h-3.5" />
                    原子定点遗忘 (Memory Forget)
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    一键撤销该记忆，写入墓碑记录防止死灰复燃，同时保持底座真实对话记录不受损。
                  </p>
                  <div>
                    <label htmlFor="forget-reason-input" className="block text-[11px] text-muted-foreground mb-1">
                      撤销理由 / 纠正说明（可选）
                    </label>
                    <input
                      id="forget-reason-input"
                      type="text"
                      value={forgetReason}
                      onChange={(e) => setForgetReason(e.target.value)}
                      placeholder="例如：方案已更迭为领域驱动设计，旧约定失效"
                      className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                    />
                  </div>
                  <div className="flex justify-end">
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      disabled={forgettingId === selectedMemory.memory_id}
                      onClick={() => handleForgetSubmit(selectedMemory.memory_id)}
                      className="text-xs focus:outline-none focus:ring-2 focus:ring-destructive"
                      data-testid="forget-memory-button"
                    >
                      <Trash2 className="w-3 h-3 mr-1" />
                      {forgettingId === selectedMemory.memory_id ? '遗忘中...' : '确认定点遗忘'}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="py-12 text-center text-xs text-muted-foreground">
              请从左侧列表选择一条记忆以查看双向溯源图谱与定点遗忘选项
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
