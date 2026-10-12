'use client';

/**
 * [INPUT]
 * @/services/memory/fourTierFts::FourTierMemoryItemDTO, FourTierMemoryScope, SaveFourTierMemoryRequestDTO
 *
 * [OUTPUT]
 * FourTierMemoryTierListView: Subview component rendering 4-tier memory categories
 * (project, session, progress, global), item inspection, deletion, and quick creation form.
 *
 * [POS]
 * Subcomponent for Item 92 (Four-Tier Persistent Memory and FTS5 Self-Maintenance Suite).
 * Strict typing applied: No `any` types allowed. Single responsibility maintained.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { FolderGit2, MessagesSquare, CheckSquare2, Globe, Trash2, Plus, Tag } from 'lucide-react';
import type {
  FourTierMemoryItemDTO,
  FourTierMemoryScope,
  SaveFourTierMemoryRequestDTO,
} from '@/services/memory/fourTierFts';

interface FourTierMemoryTierListViewProps {
  items: FourTierMemoryItemDTO[];
  selectedScope: FourTierMemoryScope;
  onSelectScope: (scope: FourTierMemoryScope) => void;
  onDeleteItem: (itemId: string) => Promise<void>;
  onSaveItem: (request: SaveFourTierMemoryRequestDTO) => Promise<void>;
}

const SCOPE_CONFIGS: {
  scope: FourTierMemoryScope;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
}[] = [
  {
    scope: 'project',
    label: '项目记忆 (Project)',
    icon: FolderGit2,
    description: '当前代码仓架构约定、设计模式与专属规则，独立落盘隔离',
  },
  {
    scope: 'session',
    label: '会话检查点 (Session)',
    icon: MessagesSquare,
    description: '长程交互断点快照与中间态决策，用于会话崩溃断点恢复',
  },
  {
    scope: 'progress',
    label: '任务进度 (Progress)',
    icon: CheckSquare2,
    description: '实时 Todo 与阶段性执行步骤，抗长上下文冲刷与遗忘',
  },
  {
    scope: 'global',
    label: '全局记忆 (Global)',
    icon: Globe,
    description: '跨项目通用的用户开发画像、沟通风格与系统偏好',
  },
];

export function FourTierMemoryTierListView({
  items,
  selectedScope,
  onSelectScope,
  onDeleteItem,
  onSaveItem,
}: FourTierMemoryTierListViewProps): React.JSX.Element {
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // New item form state
  const [newTitle, setNewTitle] = useState<string>('');
  const [newContent, setNewContent] = useState<string>('');
  const [newTags, setNewTags] = useState<string>('');

  const filteredItems = items.filter((item) => item.scope === selectedScope);
  const selectedItem = filteredItems.find((item) => item.item_id === selectedItemId) ?? filteredItems[0] ?? null;

  const handleDelete = async (itemId: string) => {
    setDeletingId(itemId);
    try {
      await onDeleteItem(itemId);
      if (selectedItemId === itemId) {
        setSelectedItemId(null);
      }
    } finally {
      setDeletingId(null);
    }
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim() || !newContent.trim()) return;
    setIsSubmitting(true);
    try {
      const tagList = newTags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);

      await onSaveItem({
        scope: selectedScope,
        title: newTitle.trim(),
        content: newContent.trim(),
        tags: tagList,
      });

      setNewTitle('');
      setNewContent('');
      setNewTags('');
      setShowAddForm(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="four-tier-memory-tier-list-view">
      {/* Scope Selector Ribbon */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {SCOPE_CONFIGS.map((cfg) => {
          const Icon = cfg.icon;
          const isCurrent = selectedScope === cfg.scope;
          const count = items.filter((i) => i.scope === cfg.scope).length;
          return (
            <button
              type="button"
              key={cfg.scope}
              onClick={() => {
                onSelectScope(cfg.scope);
                setSelectedItemId(null);
              }}
              className={`p-2.5 rounded-lg border text-left transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                isCurrent
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border/60 bg-accent/20 hover:bg-accent/40 text-foreground'
              }`}
              data-testid={`scope-tab-${cfg.scope}`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 font-semibold text-xs">
                  <Icon className="w-3.5 h-3.5" />
                  {cfg.label.split(' ')[0]}
                </div>
                <Badge variant={isCurrent ? 'default' : 'secondary'} className="text-[10px] px-1.5 py-0">
                  {count}
                </Badge>
              </div>
              <div className="mt-1 text-[11px] text-muted-foreground line-clamp-1">
                {cfg.description}
              </div>
            </button>
          );
        })}
      </div>

      {/* Action Bar */}
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          {SCOPE_CONFIGS.find((c) => c.scope === selectedScope)?.description}
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <Plus className="w-3.5 h-3.5" />
          {showAddForm ? '收起表单' : '录入新记忆'}
        </Button>
      </div>

      {/* Quick Add Form */}
      {showAddForm && (
        <form
          onSubmit={handleCreateSubmit}
          className="rounded-lg border border-primary/20 bg-primary/5 p-3 space-y-2 text-xs"
          data-testid="add-four-tier-memory-form"
        >
          <div className="font-medium text-foreground">
            新建【{SCOPE_CONFIGS.find((c) => c.scope === selectedScope)?.label}】
          </div>
          <div>
            <label htmlFor="tier-title-input" className="block text-muted-foreground mb-1 font-medium">
              记忆标题 / 标识 (Title)
            </label>
            <input
              id="tier-title-input"
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="例如：核心数据库连接池配置或当前架构决策"
              className="w-full rounded border border-border bg-background px-2.5 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              required
            />
          </div>
          <div>
            <label htmlFor="tier-content-input" className="block text-muted-foreground mb-1 font-medium">
              记忆详情内容 (Content)
            </label>
            <textarea
              id="tier-content-input"
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              rows={3}
              placeholder="例如：PostgreSQL connection pooling pool_size=20 max_overflow=10，避免长程任务断开连接。"
              className="w-full rounded border border-border bg-background px-2.5 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              required
            />
          </div>
          <div>
            <label htmlFor="tier-tags-input" className="block text-muted-foreground mb-1">
              标签（英文逗号分隔）
            </label>
            <input
              id="tier-tags-input"
              type="text"
              value={newTags}
              onChange={(e) => setNewTags(e.target.value)}
              placeholder="database, architecture, pool"
              className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          <div className="flex justify-end pt-1">
            <Button
              type="submit"
              size="sm"
              disabled={isSubmitting || !newTitle.trim() || !newContent.trim()}
              className="text-xs focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {isSubmitting ? '保存中...' : '提交沉淀'}
            </Button>
          </div>
        </form>
      )}

      {/* Main Grid: Item List & Details */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Left: List */}
        <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
          {filteredItems.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border/70 p-6 text-center text-xs text-muted-foreground">
              当前层级暂无持久记忆项
            </div>
          ) : (
            filteredItems.map((item) => {
              const isSelected = selectedItem?.item_id === item.item_id;
              return (
                <button
                  type="button"
                  key={item.item_id}
                  onClick={() => setSelectedItemId(item.item_id)}
                  className={`w-full text-left rounded-lg border p-3 cursor-pointer transition-colors text-xs focus:outline-none focus:ring-2 focus:ring-primary ${
                    isSelected
                      ? 'border-primary bg-primary/10'
                      : 'border-border/60 bg-accent/20 hover:bg-accent/40'
                  }`}
                  data-testid={`tier-item-card-${item.item_id}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="font-semibold text-foreground line-clamp-1">
                      {item.title}
                    </div>
                    <Badge variant="outline" className="shrink-0 text-[10px] uppercase">
                      {item.scope}
                    </Badge>
                  </div>
                  <div className="mt-1 text-[11px] text-muted-foreground line-clamp-2">
                    {item.content}
                  </div>
                  {item.tags.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {item.tags.map((t) => (
                        <span
                          key={t}
                          className="rounded bg-accent/40 px-1.5 py-0.2 text-[10px] text-muted-foreground flex items-center gap-0.5"
                        >
                          <Tag className="w-2.5 h-2.5" />
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </button>
              );
            })
          )}
        </div>

        {/* Right: Inspector Details */}
        <div className="rounded-lg border border-border/60 bg-accent/15 p-3 space-y-3">
          <div className="flex items-center justify-between border-b border-border/40 pb-2">
            <span className="text-xs font-semibold text-foreground">
              持久记忆切片检视器
            </span>
            {selectedItem && (
              <span className="font-mono text-[10px] text-muted-foreground">
                {selectedItem.item_id}
              </span>
            )}
          </div>

          {selectedItem ? (
            <div className="space-y-3 text-xs" data-testid="tier-item-detail-box">
              <div>
                <span className="text-muted-foreground font-medium">标题：</span>
                <div className="mt-0.5 font-semibold text-foreground text-sm">
                  {selectedItem.title}
                </div>
              </div>

              <div>
                <span className="text-muted-foreground font-medium">持久正文：</span>
                <div className="mt-1 rounded bg-background/70 p-2.5 text-foreground leading-relaxed whitespace-pre-wrap border border-border/40">
                  {selectedItem.content}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px] font-mono rounded border border-border/40 bg-background/40 p-2">
                <div>
                  <span className="text-muted-foreground">Project Hash: </span>
                  <span className="text-foreground">{selectedItem.project_hash}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Session ID: </span>
                  <span className="text-foreground">{selectedItem.session_id || '（全局/跨会话）'}</span>
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  disabled={deletingId === selectedItem.item_id}
                  onClick={() => handleDelete(selectedItem.item_id)}
                  className="text-xs focus:outline-none focus:ring-2 focus:ring-destructive"
                  data-testid="delete-tier-item-button"
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1" />
                  {deletingId === selectedItem.item_id ? '删除中...' : '删除此项'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="py-12 text-center text-xs text-muted-foreground">
              请从左侧列表选择一项以查看详细内容或执行维护
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
