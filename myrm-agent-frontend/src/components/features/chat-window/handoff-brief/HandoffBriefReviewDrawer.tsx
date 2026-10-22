/**
 * [INPUT]
 * - ./handoffBriefTypes::HandoffBrief, HandoffItem, HandoffItemCategory, HandoffInjectPayload
 * - ./useHandoffBriefStore::useHandoffBriefStore
 * - ./HandoffDecisionItemRow::HandoffDecisionItemRow
 * - lucide-react::Sparkles, Clock, Check, Plus, X, Layers, FileText
 *
 * [OUTPUT]
 * - HandoffBriefReviewDrawer: 跨会话交接简报可视化审阅与人机在环决策注入抽屉
 *
 * [POS]
 * 新建会话承接或跨会话转交时展示的 0 延迟秒开、防范大模型幻觉带偏的可视化审阅抽屉。
 */

'use client';

import React, { useState, useMemo, useCallback } from 'react';
import { Sparkles, Clock, Plus, X, Layers, FileText } from 'lucide-react';
import type { HandoffItemCategory, HandoffInjectPayload } from './handoffBriefTypes';
import { useHandoffBriefStore } from './useHandoffBriefStore';
import { HandoffDecisionItemRow } from './HandoffDecisionItemRow';

export interface HandoffBriefReviewDrawerProps {
  sessionId: string;
  onConfirmInject?: (payload: HandoffInjectPayload) => void;
  onClose?: () => void;
  className?: string;
}

export const HandoffBriefReviewDrawer: React.FC<HandoffBriefReviewDrawerProps> = ({
  sessionId,
  onConfirmInject,
  onClose,
  className = '',
}) => {
  const [filterCategory, setFilterCategory] = useState<'all' | HandoffItemCategory>('all');
  const [newContent, setNewContent] = useState('');
  const [newCategory, setNewCategory] = useState<HandoffItemCategory>('decision');
  const [customNotes, setCustomNotes] = useState('');

  const brief = useHandoffBriefStore((s) => s.briefs[sessionId]);
  const isDrawerOpen = useHandoffBriefStore((s) => s.isDrawerOpen && s.activeBriefId === sessionId);
  const closeDrawer = useHandoffBriefStore((s) => s.closeDrawer);
  const toggleItem = useHandoffBriefStore((s) => s.toggleItem);
  const toggleAllItems = useHandoffBriefStore((s) => s.toggleAllItems);
  const updateItemContent = useHandoffBriefStore((s) => s.updateItemContent);
  const addItem = useHandoffBriefStore((s) => s.addItem);
  const removeItem = useHandoffBriefStore((s) => s.removeItem);
  const buildPayload = useHandoffBriefStore((s) => s.buildPayload);

  const handleClose = useCallback(() => {
    closeDrawer();
    if (onClose) {
      onClose();
    }
  }, [closeDrawer, onClose]);

  const handleAddItem = useCallback(() => {
    const trimmed = newContent.trim();
    if (!trimmed) {
      return;
    }
    addItem(sessionId, newCategory, trimmed);
    setNewContent('');
  }, [addItem, sessionId, newCategory, newContent]);

  const handleConfirm = useCallback(() => {
    const payload = buildPayload(sessionId, customNotes);
    if (!payload) {
      return;
    }
    if (onConfirmInject) {
      onConfirmInject(payload);
    }
    handleClose();
  }, [buildPayload, sessionId, customNotes, onConfirmInject, handleClose]);

  const filteredItems = useMemo(() => {
    if (!brief) {
      return [];
    }
    if (filterCategory === 'all') {
      return brief.items;
    }
    return brief.items.filter((item) => item.category === filterCategory);
  }, [brief, filterCategory]);

  const { selectedCount, totalCount } = useMemo(() => {
    if (!brief) {
      return { selectedCount: 0, totalCount: 0 };
    }
    const sel = brief.items.filter((item) => item.enabled).length;
    return { selectedCount: sel, totalCount: brief.items.length };
  }, [brief]);

  if (!brief || !isDrawerOpen) {
    return null;
  }

  return (
    <dialog
      open
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs border-0 w-full h-full"
    >
      <section
        role="document"
        aria-label="跨会话交接简报审阅抽屉"
        className={`flex flex-col w-full max-w-2xl max-h-[90vh] rounded-xl border border-border bg-background shadow-2xl text-xs overflow-hidden ${className}`}
      >
        <header className="flex items-center justify-between px-5 py-3.5 border-b border-border/80 bg-muted/40">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="p-1.5 rounded-lg bg-primary/10 text-primary shrink-0">
              <Layers className="w-4 h-4" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-foreground truncate">
                  跨会话交接简报审阅
                </h3>
                <span className="flex items-center gap-1 px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[10px] font-mono border border-emerald-500/20 shrink-0">
                  <Clock className="w-2.5 h-2.5" aria-hidden="true" />
                  <span>{brief.precomputeDurationMs}ms 预就绪</span>
                </span>
              </div>
              <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                来源：{brief.sessionTitle} · 可视化审阅剔除幻觉
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleClose}
            className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label="关闭交接审阅抽屉"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </header>

        <div className="p-4 border-b border-border/50 bg-card/40">
          <div className="flex items-center gap-1.5 text-muted-foreground mb-1.5 font-medium text-[11px]">
            <FileText className="w-3.5 h-3.5 text-primary" aria-hidden="true" />
            <span>前序会话核心摘要</span>
          </div>
          <p className="text-xs text-foreground/90 leading-relaxed bg-background/80 p-2.5 rounded-lg border border-border/60">
            {brief.summary}
          </p>
        </div>

        <div className="flex items-center justify-between px-5 py-2 bg-muted/20 border-b border-border/50 text-[11px]">
          <div className="flex items-center gap-1">
            {(['all', 'decision', 'todo', 'constraint'] as const).map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => {
                  setFilterCategory(cat);
                }}
                className={`px-2 py-0.5 rounded transition-colors ${
                  filterCategory === cat
                    ? 'bg-primary text-primary-foreground font-medium'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                {cat === 'all' ? '全部' : cat === 'decision' ? '决策' : cat === 'todo' ? '待办' : '约束'}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 text-muted-foreground">
            <span>
              已选 {selectedCount} / {totalCount} 项
            </span>
            <button
              type="button"
              onClick={() => {
                toggleAllItems(sessionId, selectedCount < totalCount);
              }}
              className="text-primary hover:underline"
            >
              {selectedCount < totalCount ? '全选' : '清空'}
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {filteredItems.length === 0 ? (
            <div className="text-center py-6 text-muted-foreground text-xs">
              无该分类条目
            </div>
          ) : (
            <ul className="space-y-1.5">
              {filteredItems.map((item) => (
                <HandoffDecisionItemRow
                  key={item.id}
                  item={item}
                  onToggle={() => {
                    toggleItem(sessionId, item.id);
                  }}
                  onUpdate={(content) => {
                    updateItemContent(sessionId, item.id, content);
                  }}
                  onRemove={() => {
                    removeItem(sessionId, item.id);
                  }}
                />
              ))}
            </ul>
          )}

          <div className="mt-3 pt-3 border-t border-border/40 flex items-center gap-1.5">
            <select
              value={newCategory}
              onChange={(e) => {
                setNewCategory(e.target.value as HandoffItemCategory);
              }}
              className="rounded border border-input bg-background px-2 py-1 text-xs text-foreground focus:outline-none"
              aria-label="选择补充条目类型"
            >
              <option value="decision">决策</option>
              <option value="todo">待办</option>
              <option value="constraint">约束</option>
            </select>
            <input
              type="text"
              value={newContent}
              onChange={(e) => {
                setNewContent(e.target.value);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAddItem();
                }
              }}
              placeholder="补充一条决策、约束或待办..."
              className="flex-1 rounded border border-input bg-background px-2.5 py-1 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary"
              aria-label="补充条目内容"
            />
            <button
              type="button"
              onClick={handleAddItem}
              disabled={!newContent.trim()}
              className="flex items-center gap-1 px-2.5 py-1 rounded bg-secondary text-secondary-foreground hover:bg-secondary/80 disabled:opacity-50 text-[11px] font-medium transition-colors"
            >
              <Plus className="w-3.5 h-3.5" aria-hidden="true" />
              <span>添加</span>
            </button>
          </div>

          <div className="mt-3">
            <textarea
              value={customNotes}
              onChange={(e) => {
                setCustomNotes(e.target.value);
              }}
              placeholder="附加给新会话的额外人机指示（可选）..."
              rows={2}
              className="w-full resize-none rounded-lg border border-input bg-background/50 px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary"
              aria-label="附加额外指示"
            />
          </div>
        </div>

        <footer className="flex items-center justify-between px-5 py-3 border-t border-border/80 bg-muted/30">
          <span className="text-[11px] text-muted-foreground">
            确认后将结构化注入新会话上下文
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleClose}
              className="px-3 py-1.5 rounded text-xs text-muted-foreground hover:bg-muted transition-colors"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={selectedCount === 0}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors shadow-xs"
            >
              <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
              <span>确认注入新会话</span>
            </button>
          </div>
        </footer>
      </section>
    </dialog>
  );
};
