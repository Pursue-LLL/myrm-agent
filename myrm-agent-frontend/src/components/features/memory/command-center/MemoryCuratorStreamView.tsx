'use client';

/**
 * [INPUT]
 * @/services/memory/curatorStudio::CuratedMemoryEntryDTO, CurateEntryRequest,
 *   UpdateCurateEntryRequest, CuratedMemoryCategory, CuratedMemoryStatus
 * ./MemoryCuratorAddForm::MemoryCuratorAddForm
 * ./MemoryCuratorEntryCard::MemoryCuratorEntryCard
 *
 * [OUTPUT]
 * MemoryCuratorStreamView: Subview providing a WYSIWYG card stream curator studio,
 * anti-misremembering human confirmation gate, tag manager, and search filtering.
 *
 * [POS]
 * Subcomponent for Item 101 (HumanReadableMarkdownBidiSyncAndMemoryCuratorStudioSuite).
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import React, { useState } from 'react';
import { Button } from '@/components/primitives/button';
import { Search, PlusCircle } from 'lucide-react';
import type {
  CuratedMemoryEntryDTO,
  CurateEntryRequest,
  UpdateCurateEntryRequest,
} from '@/services/memory/curatorStudio';
import { MemoryCuratorAddForm } from './MemoryCuratorAddForm';
import { MemoryCuratorEntryCard } from './MemoryCuratorEntryCard';

interface MemoryCuratorStreamViewProps {
  entries: CuratedMemoryEntryDTO[];
  onCreateEntry: (request: CurateEntryRequest) => Promise<void>;
  onUpdateEntry: (entryId: string, request: UpdateCurateEntryRequest) => Promise<void>;
  onAuditEntry: (entryId: string, isApproved: boolean) => Promise<void>;
  onEraseEntry: (entryId: string, hardErase: boolean) => Promise<void>;
  isLoading: boolean;
}

export function MemoryCuratorStreamView({
  entries,
  onCreateEntry,
  onUpdateEntry,
  onAuditEntry,
  onEraseEntry,
  isLoading,
}: MemoryCuratorStreamViewProps): React.JSX.Element {
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isAdding, setIsAdding] = useState<boolean>(false);

  const filteredEntries = entries.filter((item) => {
    if (selectedCategory !== 'all' && item.category !== selectedCategory) return false;
    if (selectedStatus !== 'all' && item.status !== selectedStatus) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchTitle = item.title.toLowerCase().includes(q);
      const matchContent = item.content.toLowerCase().includes(q);
      const matchTag = item.tags.some((t) => t.toLowerCase().includes(q));
      if (!matchTitle && !matchContent && !matchTag) return false;
    }
    return true;
  });

  return (
    <div className="space-y-4">
      {/* Search and Filters Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border-subtle bg-surface p-3">
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-text-tertiary" />
          <input
            type="text"
            placeholder="搜索记忆标题、内容或标签..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg border border-border-subtle bg-surface-subtle pl-9 pr-3 py-1.5 text-xs text-text-primary focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary"
            aria-label="搜索记忆"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Category Filter Pills */}
          <div className="flex items-center rounded-lg border border-border-subtle bg-surface-subtle p-0.5 text-xs">
            {['all', 'preference', 'fact', 'procedure', 'experience'].map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setSelectedCategory(cat)}
                className={`rounded-md px-2.5 py-1 capitalize transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                  selectedCategory === cat
                    ? 'bg-surface font-medium text-text-primary shadow-xs'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
                aria-label={`按分类筛选 ${cat}`}
              >
                {cat === 'all' ? '全部分类' : cat}
              </button>
            ))}
          </div>

          {/* Status Filter */}
          <div className="flex items-center rounded-lg border border-border-subtle bg-surface-subtle p-0.5 text-xs">
            {['all', 'confirmed', 'pending_confirmation', 'archived'].map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => setSelectedStatus(st)}
                className={`rounded-md px-2 py-1 transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                  selectedStatus === st
                    ? 'bg-surface font-medium text-text-primary shadow-xs'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
                aria-label={`按状态筛选 ${st}`}
              >
                {st === 'all'
                  ? '全部状态'
                  : st === 'confirmed'
                    ? '已生效'
                    : st === 'pending_confirmation'
                      ? '待审核'
                      : '已归档'}
              </button>
            ))}
          </div>

          <Button
            type="button"
            size="sm"
            onClick={() => setIsAdding(!isAdding)}
            className="flex items-center gap-1 bg-primary text-primary-foreground hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary"
            aria-label="添加新记忆条目"
          >
            <PlusCircle className="h-3.5 w-3.5" />
            <span>新增记忆</span>
          </Button>
        </div>
      </div>

      {/* Collapsible Add Entry Form */}
      <MemoryCuratorAddForm
        isOpen={isAdding}
        onClose={() => setIsAdding(false)}
        onSubmit={onCreateEntry}
        isLoading={isLoading}
      />

      {/* Card Stream Grid */}
      <div className="space-y-3">
        {filteredEntries.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border-subtle p-8 text-center text-text-secondary text-xs">
            暂无匹配的记忆条目，可通过上方输入框新增或热重载 Markdown 镜像。
          </div>
        ) : (
          filteredEntries.map((item) => (
            <MemoryCuratorEntryCard
              key={item.entry_id}
              item={item}
              onUpdate={onUpdateEntry}
              onAudit={onAuditEntry}
              onErase={onEraseEntry}
            />
          ))
        )}
      </div>
    </div>
  );
}
