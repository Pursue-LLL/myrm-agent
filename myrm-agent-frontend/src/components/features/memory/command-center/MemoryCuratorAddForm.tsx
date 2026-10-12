'use client';

/**
 * [INPUT]
 * @/services/memory/curatorStudio::CurateEntryRequest, CuratedMemoryCategory
 *
 * [OUTPUT]
 * MemoryCuratorAddForm: Lightweight collapsible form component for registering curated memories.
 *
 * [POS]
 * Subcomponent for Item 101 (HumanReadableMarkdownBidiSyncAndMemoryCuratorStudioSuite).
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import React, { useState } from 'react';
import { Button } from '@/components/primitives/button';
import { Sparkles, X } from 'lucide-react';
import type {
  CuratedMemoryCategory,
  CurateEntryRequest,
} from '@/services/memory/curatorStudio';

interface MemoryCuratorAddFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (request: CurateEntryRequest) => Promise<void>;
  isLoading: boolean;
}

export function MemoryCuratorAddForm({
  isOpen,
  onClose,
  onSubmit,
  isLoading,
}: MemoryCuratorAddFormProps): React.JSX.Element | null {
  const [newTitle, setNewTitle] = useState<string>('');
  const [newCategory, setNewCategory] = useState<CuratedMemoryCategory>('fact');
  const [newContent, setNewContent] = useState<string>('');
  const [newTags, setNewTags] = useState<string>('');

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!newTitle.trim() || !newContent.trim()) return;

    const tagsList = newTags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    await onSubmit({
      title: newTitle.trim(),
      category: newCategory,
      content: newContent.trim(),
      tags: tagsList,
      confidence: 1.0,
      status: 'confirmed',
    });

    setNewTitle('');
    setNewContent('');
    setNewTags('');
    onClose();
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-3"
    >
      <div className="flex items-center justify-between">
        <span className="font-semibold text-text-primary text-sm flex items-center gap-1.5">
          <Sparkles className="h-4 w-4 text-primary" />
          策展新记忆 (保存后自动同步至工作区 Markdown)
        </span>
        <button
          type="button"
          onClick={onClose}
          className="text-text-secondary hover:text-text-primary focus:outline-none focus:ring-2 focus:ring-primary rounded"
          aria-label="关闭新增表单"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label htmlFor="new-entry-title" className="block text-xs font-medium text-text-secondary mb-1">
            记忆标题
          </label>
          <input
            id="new-entry-title"
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="例如: 界面深色主题偏好"
            className="w-full rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs text-text-primary focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary"
            required
          />
        </div>

        <div>
          <label htmlFor="new-entry-category" className="block text-xs font-medium text-text-secondary mb-1">
            认知分类
          </label>
          <select
            id="new-entry-category"
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value as CuratedMemoryCategory)}
            className="w-full rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs text-text-primary focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="preference">偏好 (Preference)</option>
            <option value="fact">事实 (Fact)</option>
            <option value="procedure">程序 (Procedure)</option>
            <option value="experience">经验 (Experience)</option>
          </select>
        </div>

        <div>
          <label htmlFor="new-entry-tags" className="block text-xs font-medium text-text-secondary mb-1">
            标签 (逗号分隔)
          </label>
          <input
            id="new-entry-tags"
            type="text"
            value={newTags}
            onChange={(e) => setNewTags(e.target.value)}
            placeholder="ui, theme, dark-mode"
            className="w-full rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs text-text-primary focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
      </div>

      <div>
        <label htmlFor="new-entry-content" className="block text-xs font-medium text-text-secondary mb-1">
          详细描述内容
        </label>
        <textarea
          id="new-entry-content"
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          rows={2}
          placeholder="用户明确要求界面使用深色主题，并在暗色环境下保持高对比度文字排版。"
          className="w-full rounded-md border border-border-subtle bg-surface p-2 text-xs text-text-primary focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary"
          required
        />
      </div>

      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onClose}
          className="focus:outline-none focus:ring-2 focus:ring-primary"
        >
          取消
        </Button>
        <Button
          type="submit"
          size="sm"
          disabled={isLoading || !newTitle.trim() || !newContent.trim()}
          className="bg-primary text-primary-foreground hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary"
        >
          确认保存
        </Button>
      </div>
    </form>
  );
}
