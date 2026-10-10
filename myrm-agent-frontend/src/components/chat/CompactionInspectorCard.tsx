/**
 * [INPUT]
 * - CompactionInspectorCardProps:
 *   - data: CompactionInspectorCardData (preTokens, postTokens, savedTokens, savingsRatio, summary, keyDecisions, pinnedItems)
 *   - onSaveSummary?: (newSummary: string) => void
 *
 * [OUTPUT]
 * - CompactionInspectorCard: React component rendering transparent compaction statistics,
 *   expandable structured summary with inline editing, and pinned context guarantees.
 *
 * [POS]
 * UI card for TransparentCompactionInspectorAndContextPinningCard (Item 146).
 * Eliminates blackbox compaction surprises by rendering visible token savings and zero-pruning pins.
 */

import React, { useState } from 'react';

export interface CompactionInspectorCardData {
  readonly cardId: string;
  readonly chatId: string;
  readonly preTokens: number;
  readonly postTokens: number;
  readonly savedTokens: number;
  readonly savingsRatio: number;
  readonly compactedTurnsCount: number;
  readonly preservedPinnedCount: number;
  readonly structuredSummaryText: string;
  readonly keyDecisions?: ReadonlyArray<string>;
  readonly pinnedItemsPreview?: ReadonlyArray<string>;
  readonly isUserEditable?: boolean;
}

export interface CompactionInspectorCardProps {
  readonly data: CompactionInspectorCardData;
  readonly onSaveSummary?: (newSummary: string) => void;
  readonly className?: string;
}

export const CompactionInspectorCard: React.FC<CompactionInspectorCardProps> = ({
  data,
  onSaveSummary,
  className = '',
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [summaryDraft, setSummaryDraft] = useState(data.structuredSummaryText);

  const percentSaved = Math.round(data.savingsRatio * 100);

  const handleSave = () => {
    setIsEditing(false);
    if (onSaveSummary) {
      onSaveSummary(summaryDraft);
    }
  };

  const handleCancel = () => {
    setSummaryDraft(data.structuredSummaryText);
    setIsEditing(false);
  };

  return (
    <div
      data-testid="compaction-inspector-card"
      className={`my-3 rounded-lg border border-border/80 bg-muted/40 p-3 text-xs shadow-sm transition-all ${className}`}
    >
      {/* Header bar */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-primary">
            ⚡
          </span>
          <span className="font-medium text-foreground">
            上下文透明压缩完成
          </span>
          <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
            节省 {percentSaved}%
          </span>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-muted-foreground text-[11px]">
            {data.preTokens.toLocaleString()} → {data.postTokens.toLocaleString()} tokens
          </span>
          <button
            type="button"
            data-testid="toggle-expand-btn"
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-primary hover:underline font-medium text-[11px] focus:outline-none"
          >
            {isExpanded ? '收起详情 ▲' : '查看详情 ▼'}
          </button>
        </div>
      </div>

      {/* Metric badges */}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
        <span className="rounded border border-border/50 bg-background/50 px-2 py-0.5">
          释放 Token: <strong className="text-foreground">{data.savedTokens.toLocaleString()}</strong>
        </span>
        <span className="rounded border border-border/50 bg-background/50 px-2 py-0.5">
          折叠历史轮次: <strong className="text-foreground">{data.compactedTurnsCount}</strong>
        </span>
        <span className="rounded border border-border/50 bg-background/50 px-2 py-0.5">
          📌 锁定保留: <strong className="text-foreground">{data.preservedPinnedCount} 项</strong>
        </span>
      </div>

      {/* Expanded Details Body */}
      {isExpanded && (
        <div data-testid="expanded-details" className="mt-3 border-t border-border/50 pt-2.5">
          {/* Structured Summary Section */}
          <div className="mb-2.5">
            <div className="flex items-center justify-between mb-1">
              <span className="font-semibold text-foreground">结构化会话摘要：</span>
              {data.isUserEditable !== false && !isEditing && (
                <button
                  type="button"
                  data-testid="edit-summary-btn"
                  onClick={() => setIsEditing(true)}
                  className="text-primary hover:underline text-[11px]"
                >
                  微调摘要 ✏️
                </button>
              )}
            </div>

            {isEditing ? (
              <div className="flex flex-col gap-1.5">
                <textarea
                  data-testid="summary-textarea"
                  value={summaryDraft}
                  onChange={(e) => setSummaryDraft(e.target.value)}
                  className="w-full rounded border border-border bg-background p-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  rows={3}
                />
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={handleCancel}
                    className="rounded px-2 py-1 text-[11px] text-muted-foreground hover:bg-muted"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    data-testid="save-summary-btn"
                    onClick={handleSave}
                    className="rounded bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground hover:bg-primary/90"
                  >
                    保存微调
                  </button>
                </div>
              </div>
            ) : (
              <p
                data-testid="summary-text"
                className="whitespace-pre-wrap rounded bg-background/80 p-2 text-foreground/90 font-mono text-[11px] leading-relaxed border border-border/40"
              >
                {summaryDraft}
              </p>
            )}
          </div>

          {/* Key Decisions list */}
          {data.keyDecisions && data.keyDecisions.length > 0 && (
            <div className="mb-2">
              <span className="font-semibold text-foreground">关键决策与硬约束：</span>
              <ul className="mt-1 list-disc pl-4 space-y-0.5 text-foreground/80">
                {data.keyDecisions.map((decision, idx) => (
                  <li key={idx}>{decision}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Pinned Items preview */}
          {data.pinnedItemsPreview && data.pinnedItemsPreview.length > 0 && (
            <div>
              <span className="font-semibold text-foreground">零裁切锁定项 (Zero-Pruning Guarantees)：</span>
              <div className="mt-1 flex flex-col gap-1">
                {data.pinnedItemsPreview.map((item, idx) => (
                  <span
                    key={idx}
                    className="rounded bg-accent/40 px-2 py-1 text-[11px] text-foreground border border-border/30"
                  >
                    {item}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
