/**
 * [INPUT]
 * - ./handoffBriefTypes::HandoffItem, HandoffItemCategory
 * - lucide-react::CheckSquare, Square, Edit2, Check, X, Trash2
 *
 * [OUTPUT]
 * - HandoffDecisionItemRow: 跨会话简报单条决策/待办/约束可编辑行组件
 *
 * [POS]
 * 在交接审阅抽屉中渲染单条条目，提供复选框开关、行内实时编辑修改与删除能力。
 */

'use client';

import React, { useState, useCallback } from 'react';
import { CheckSquare, Square, Edit2, Check, X, Trash2 } from 'lucide-react';
import type { HandoffItem, HandoffItemCategory } from './handoffBriefTypes';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';

export interface HandoffDecisionItemRowProps {
  item: HandoffItem;
  onToggle: () => void;
  onUpdate: (content: string) => void;
  onRemove?: () => void;
  className?: string;
}

function getCategoryBadge(cat: HandoffItemCategory): { label: string; className: string } {
  switch (cat) {
    case 'decision':
      return { label: '决策', className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20' };
    case 'todo':
      return { label: '待办', className: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20' };
    case 'constraint':
      return { label: '约束', className: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20' };
    case 'artifact':
    default:
      return { label: '产物', className: 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20' };
  }
}

export const HandoffDecisionItemRow: React.FC<HandoffDecisionItemRowProps> = ({
  item,
  onToggle,
  onUpdate,
  onRemove,
  className = '',
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(item.content);

  const badge = getCategoryBadge(item.category);

  const handleSave = useCallback(() => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== item.content) {
      onUpdate(trimmed);
    }
    setIsEditing(false);
  }, [editValue, item.content, onUpdate]);

  const handleCancel = useCallback(() => {
    setEditValue(item.content);
    setIsEditing(false);
  }, [item.content]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleSave();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        handleCancel();
      }
    },
    [handleSave, handleCancel]
  );

  return (
    <li
      className={`group flex items-start gap-2.5 p-2.5 rounded-lg border transition-all text-xs ${
        item.enabled
          ? 'bg-card/80 border-border/70 hover:border-border'
          : 'bg-muted/30 border-border/30 opacity-60'
      } ${className}`}
    >
      <button
        type="button"
        onClick={onToggle}
        className="mt-0.5 text-muted-foreground hover:text-primary transition-colors shrink-0"
        aria-label={item.enabled ? '取消勾选该条目' : '勾选包含该条目'}
      >
        {item.enabled ? (
          <CheckSquare className="w-4 h-4 text-primary" aria-hidden="true" />
        ) : (
          <Square className="w-4 h-4 text-muted-foreground/60" aria-hidden="true" />
        )}
      </button>

      <span
        className={`px-1.5 py-0.2 rounded border text-[10px] font-medium shrink-0 mt-0.5 ${badge.className}`}
      >
        {badge.label}
      </span>

      <div className="flex-1 min-w-0">
        {isEditing ? (
          <div className="flex items-center gap-1.5 w-full">
            <input
              type="text"
              value={editValue}
              onChange={(e) => {
                setEditValue(e.target.value);
              }}
              onKeyDown={handleKeyDown}
              className="flex-1 rounded border border-primary/50 bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-sans"
              aria-label="编辑条目描述"
            />
            <button
              type="button"
              onClick={handleSave}
              className="p-1 rounded bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shrink-0"
              aria-label="保存修改"
            >
              <Check className="w-3.5 h-3.5" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={handleCancel}
              className="p-1 rounded text-muted-foreground hover:bg-muted transition-colors shrink-0"
              aria-label="取消修改"
            >
              <X className="w-3.5 h-3.5" aria-hidden="true" />
            </button>
          </div>
        ) : (
          <p
            className={`text-xs leading-relaxed break-words ${
              item.enabled ? 'text-foreground' : 'text-muted-foreground line-through'
            }`}
          >
            {item.content}
          </p>
        )}
      </div>

      {!isEditing && (
        <div className={`flex items-center gap-1 ${REVEAL_ON_HOVER} transition-opacity shrink-0`}>
          <button
            type="button"
            onClick={() => {
              setIsEditing(true);
            }}
            className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label="编辑此条目"
          >
            <Edit2 className="w-3 h-3" aria-hidden="true" />
          </button>
          {onRemove && (
            <button
              type="button"
              onClick={onRemove}
              className="p-1 rounded text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 transition-colors"
              aria-label="删除此条目"
            >
              <Trash2 className="w-3 h-3" aria-hidden="true" />
            </button>
          )}
        </div>
      )}
    </li>
  );
};
