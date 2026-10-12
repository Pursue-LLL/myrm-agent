'use client';

/**
 * [INPUT]
 * @/services/memory/curatorStudio::CuratedMemoryEntryDTO, UpdateCurateEntryRequest, CuratedMemoryCategory
 *
 * [OUTPUT]
 * MemoryCuratorEntryCard: Self-contained card representing a single curated memory item,
 * supporting in-place editing, human audit gate confirmations, and one-click privacy wiping.
 *
 * [POS]
 * Subcomponent for Item 101 (HumanReadableMarkdownBidiSyncAndMemoryCuratorStudioSuite).
 * Strict typing applied: No `any` types allowed. Single file < 250 lines.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  Check,
  X,
  Trash2,
  Edit2,
  Tag,
  ShieldAlert,
} from 'lucide-react';
import type {
  CuratedMemoryCategory,
  CuratedMemoryEntryDTO,
  UpdateCurateEntryRequest,
} from '@/services/memory/curatorStudio';

interface MemoryCuratorEntryCardProps {
  item: CuratedMemoryEntryDTO;
  onUpdate: (entryId: string, request: UpdateCurateEntryRequest) => Promise<void>;
  onAudit: (entryId: string, isApproved: boolean) => Promise<void>;
  onErase: (entryId: string, hardErase: boolean) => Promise<void>;
}

export function MemoryCuratorEntryCard({
  item,
  onUpdate,
  onAudit,
  onErase,
}: MemoryCuratorEntryCardProps): React.JSX.Element {
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editTitle, setEditTitle] = useState<string>(item.title);
  const [editContent, setEditContent] = useState<string>(item.content);

  const isPending = item.status === 'pending_confirmation';

  const handleSaveEdit = async () => {
    if (!editTitle.trim() || !editContent.trim()) return;
    await onUpdate(item.entry_id, {
      title: editTitle.trim(),
      content: editContent.trim(),
    });
    setIsEditing(false);
  };

  const getCategoryBadgeClass = (category: CuratedMemoryCategory): string => {
    switch (category) {
      case 'preference':
        return 'bg-purple-500/10 text-purple-600 border-purple-200';
      case 'fact':
        return 'bg-blue-500/10 text-blue-600 border-blue-200';
      case 'procedure':
        return 'bg-amber-500/10 text-amber-600 border-amber-200';
      case 'experience':
        return 'bg-emerald-500/10 text-emerald-600 border-emerald-200';
      default:
        return 'bg-surface-subtle text-text-secondary';
    }
  };

  return (
    <div
      className={`rounded-xl border p-4 transition-all shadow-xs ${
        isPending
          ? 'border-amber-400/50 bg-amber-500/5'
          : 'border-border-subtle bg-surface hover:border-border'
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className={`text-xs font-medium ${getCategoryBadgeClass(item.category)}`}>
            {item.category}
          </Badge>

          {isPending ? (
            <Badge variant="outline" className="bg-amber-500/10 text-amber-600 border-amber-300 text-xs flex items-center gap-1">
              <ShieldAlert className="h-3 w-3" />
              待人类门禁确认
            </Badge>
          ) : item.status === 'archived' ? (
            <Badge variant="outline" className="bg-surface-subtle text-text-tertiary text-xs">
              已归档
            </Badge>
          ) : (
            <Badge variant="outline" className="bg-emerald-500/10 text-emerald-600 border-emerald-200 text-xs">
              已生效
            </Badge>
          )}

          <span className="font-mono text-text-tertiary text-xs">
            置信度: {(item.confidence * 100).toFixed(0)}%
          </span>
        </div>

        {/* Actions toolbar */}
        <div className="flex items-center gap-1.5">
          {isPending && (
            <>
              <button
                type="button"
                onClick={() => void onAudit(item.entry_id, true)}
                className="flex items-center gap-1 rounded bg-emerald-600 px-2 py-1 text-xs font-medium text-white hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                aria-label={`确认记忆 ${item.title}`}
              >
                <Check className="h-3 w-3" />
                <span>确认采纳</span>
              </button>
              <button
                type="button"
                onClick={() => void onAudit(item.entry_id, false)}
                className="flex items-center gap-1 rounded bg-rose-600 px-2 py-1 text-xs font-medium text-white hover:bg-rose-700 focus:outline-none focus:ring-2 focus:ring-rose-500"
                aria-label={`驳回记忆 ${item.title}`}
              >
                <X className="h-3 w-3" />
                <span>驳回</span>
              </button>
            </>
          )}

          <button
            type="button"
            onClick={() => setIsEditing(!isEditing)}
            className="rounded p-1 text-text-secondary hover:bg-surface-subtle hover:text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
            aria-label={`编辑记忆 ${item.title}`}
          >
            <Edit2 className="h-3.5 w-3.5" />
          </button>

          <button
            type="button"
            onClick={() => void onErase(item.entry_id, true)}
            className="rounded p-1 text-text-secondary hover:bg-rose-500/10 hover:text-rose-600 focus:outline-none focus:ring-2 focus:ring-rose-500"
            aria-label={`一键擦除记忆 ${item.title}`}
            title="一键物理抹除并同步删除 Markdown"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Content section */}
      {isEditing ? (
        <div className="mt-3 space-y-2">
          <input
            type="text"
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            className="w-full rounded border border-border-subtle bg-surface-subtle px-2.5 py-1 text-xs font-semibold text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
            aria-label="编辑标题"
          />
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            rows={2}
            className="w-full rounded border border-border-subtle bg-surface-subtle p-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
            aria-label="编辑内容"
          />
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsEditing(false)}
              className="focus:outline-none focus:ring-2 focus:ring-primary"
            >
              取消
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => void handleSaveEdit()}
              className="bg-primary text-primary-foreground hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary"
            >
              保存更新
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-2 space-y-1">
          <h4 className="font-semibold text-text-primary text-xs">{item.title}</h4>
          <p className="text-text-secondary text-xs leading-relaxed">{item.content}</p>

          {item.tags.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              {item.tags.map((tg) => (
                <span
                  key={tg}
                  className="inline-flex items-center gap-1 rounded bg-surface-subtle px-1.5 py-0.5 text-text-tertiary text-[10px]"
                >
                  <Tag className="h-2.5 w-2.5" />
                  {tg}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
