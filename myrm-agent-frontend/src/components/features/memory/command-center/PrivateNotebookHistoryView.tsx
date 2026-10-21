'use client';

/**
 * [INPUT]
 * @/services/memory/privateNotebook::HistoryContextItemDTO, HistoryEntryItemDTO
 *
 * [OUTPUT]
 * PrivateNotebookHistoryView: Subcomponent for cross-context interaction history search and archived context listing.
 *
 * [POS]
 * Subcomponent for Item 89 (Transparent Inspectable Model Private Notebook Suite).
 * Strict typing applied: No `any` types allowed.
 */

import React, { useState } from 'react';
import { Button } from '@/components/primitives/button';
import { Search } from 'lucide-react';
import {
  searchHistory,
  listContexts,
  type HistoryContextItemDTO,
  type HistoryEntryItemDTO,
} from '@/services/memory/privateNotebook';

interface PrivateNotebookHistoryViewProps {
  historyContexts: HistoryContextItemDTO[];
  onRefreshContexts: () => Promise<void>;
}

export function PrivateNotebookHistoryView({
  historyContexts,
  onRefreshContexts,
}: PrivateNotebookHistoryViewProps): React.JSX.Element {
  const [historySearchQuery, setHistorySearchQuery] = useState<string>('');
  const [historySearchResults, setHistorySearchResults] = useState<HistoryEntryItemDTO[]>([]);
  const [isSearchingHistory, setIsSearchingHistory] = useState<boolean>(false);

  const handleSearchHistory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!historySearchQuery.trim()) {
      setHistorySearchResults([]);
      return;
    }
    setIsSearchingHistory(true);
    try {
      const results = await searchHistory(historySearchQuery.trim());
      setHistorySearchResults(results);
    } catch {
      setHistorySearchResults([]);
    } finally {
      setIsSearchingHistory(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="private-notebook-history-view">
      <form onSubmit={handleSearchHistory} className="flex gap-2 items-center">
        <label htmlFor="search-history-input" className="sr-only">
          检索跨窗口交互流
        </label>
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
          <input
            id="search-history-input"
            type="text"
            placeholder="搜索历史所有上下文窗口中的用户提示、模型回复与工具调用..."
            value={historySearchQuery}
            onChange={(e) => setHistorySearchQuery(e.target.value)}
            className="w-full rounded border border-input bg-background pl-8 pr-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
        </div>
        <Button
          type="submit"
          size="sm"
          variant="secondary"
          className="h-7 text-xs"
          disabled={isSearchingHistory}
          data-testid="search-history-btn"
        >
          {isSearchingHistory ? '检索中...' : '检索历史'}
        </Button>
      </form>

      {historySearchResults.length > 0 && (
        <div className="space-y-1.5 max-h-52 overflow-y-auto">
          {historySearchResults.map((hr, idx) => (
            <div
              key={`${hr.context_id}-${hr.turn_index}-${idx}`}
              className="rounded border border-border/50 p-2 bg-card text-xs space-y-0.5"
            >
              <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                <span>
                  [{hr.context_id}] Turn #{hr.turn_index} ({hr.role})
                </span>
                <span>{hr.created_at ? hr.created_at.slice(0, 19).replace('T', ' ') : ''}</span>
              </div>
              <div className="text-foreground font-mono whitespace-pre-wrap">{hr.content}</div>
            </div>
          ))}
        </div>
      )}

      <div className="rounded border border-border/60 p-2.5 bg-muted/20 space-y-1.5">
        <div className="text-xs font-semibold text-foreground flex items-center justify-between">
          <span>归档上下文窗口 ({historyContexts.length})</span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void onRefreshContexts()}
            className="h-6 text-[10px]"
            data-testid="refresh-contexts-btn"
          >
            刷新
          </Button>
        </div>
        <div className="space-y-1 max-h-36 overflow-y-auto">
          {historyContexts.length > 0 ? (
            historyContexts.map((ctx) => (
              <div
                key={ctx.context_id}
                className="flex items-center justify-between p-1.5 rounded bg-background border border-border/40 text-xs"
              >
                <span className="font-medium text-foreground">{ctx.context_id}</span>
                <span className="text-[10px] text-muted-foreground">{ctx.turn_count} 轮交互</span>
              </div>
            ))
          ) : (
            <div className="text-center py-2 text-muted-foreground text-xs">
              暂无已归档的历史上下文窗口
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
