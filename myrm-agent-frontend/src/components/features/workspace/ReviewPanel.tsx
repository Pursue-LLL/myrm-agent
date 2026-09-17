'use client';

/**
 * [INPUT]
 * - @/lib/utils/pathValidation::formatPathForDisplay (POS: 工作区路径规范与展示截断)
 * - @/lib/utils/imeUtils::isImeComposing (POS: 输入法组合输入状态检测)
 * - @/services/chat::getMessages (POS: 会话历史消息加载服务)
 * - ./ReviewDiffRow::ReviewDiffRow (POS: workspace 审查面板的单文件行组件)
 *
 * [OUTPUT]
 * - ReviewPanel: 变更审阅与会话反馈侧栏组件
 *
 * [POS]
 * 工作区审阅面板。文件头列表虚拟化（千文件不卡）、检索与状态过滤、
 * 大文件 Diff 折叠与一键复制、服务端截断感知、工作区路径徽章及消息反馈。
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  ChevronDown,
  RefreshCw,
  MessageSquare,
  MessagesSquare,
  User,
  Bot,
  FileEdit,
  Search,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { isImeComposing } from '@/lib/utils/imeUtils';
import { formatPathForDisplay } from '@/lib/utils/pathValidation';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import { getMessages } from '@/services/chat';
import type { Message } from '@/store/chat/types';
import ReviewDiffRow, { reviewRowKey, type ReviewFileDiff } from './ReviewDiffRow';

interface ReviewPanelProps {
  sessionId: string | null;
  messageId?: string;
  workspacePath?: string | null;
  onSendFeedback?: (chatId: string, feedback: string) => void;
}

type ReviewTab = 'diff' | 'messages';
type StatusFilter = 'all' | 'create' | 'modify';

function MessagePreview({ chatId }: { chatId: string }) {
  const t = useTranslations('multiPane');
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchMessages = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getMessages(chatId, { limit: 20 });
      setMessages(data.messages);
    } catch {
      // Silently handle
    } finally {
      setLoading(false);
    }
  }, [chatId]);

  useEffect(() => {
    fetchMessages();
  }, [fetchMessages]);

  if (loading && messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
        <RefreshCw size={14} className="animate-spin mr-2" />
        {t('loadingMessages')}
      </div>
    );
  }

  if (messages.length === 0) {
    return <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">{t('noMessages')}</div>;
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-end px-4 py-2 border-b border-border/30">
        <button
          onClick={fetchMessages}
          disabled={loading}
          className="p-1.5 rounded-full hover:bg-muted transition-colors text-muted-foreground"
        >
          <RefreshCw size={14} className={cn(loading && 'animate-spin')} />
        </button>
      </div>
      <div className="flex-1 overflow-auto px-4 py-3 space-y-3">
        {messages.map((msg) => (
          <div key={msg.messageId} className={cn('flex gap-2', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
            {msg.role === 'assistant' && <Bot size={16} className="text-primary mt-1 shrink-0" />}
            <div
              className={cn(
                'max-w-[85%] rounded-lg px-3 py-2 text-xs',
                msg.role === 'user' ? 'bg-primary/10 text-foreground' : 'bg-muted/50 text-foreground',
              )}
            >
              <p className="whitespace-pre-wrap break-words line-clamp-10">{msg.content || '...'}</p>
            </div>
            {msg.role === 'user' && <User size={16} className="text-muted-foreground mt-1 shrink-0" />}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ReviewPanel({ sessionId, messageId, workspacePath, onSendFeedback }: ReviewPanelProps) {
  const t = useTranslations('multiPane');
  const [activeTab, setActiveTab] = useState<ReviewTab>('diff');
  const [diffs, setDiffs] = useState<ReviewFileDiff[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());
  const [expandedLongDiffs, setExpandedLongDiffs] = useState<Set<string>>(new Set());
  const [copiedFile, setCopiedFile] = useState<string | null>(null);
  const [feedbackText, setFeedbackText] = useState('');
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const parentRef = useRef<HTMLDivElement>(null);

  const fetchDiffs = useCallback(async () => {
    if (!sessionId) {
      return;
    }
    setLoading(true);
    try {
      const url = messageId
        ? `${getBackendUrl()}/api/v1/files/revert/diff/${sessionId}/${messageId}`
        : `${getBackendUrl()}/api/v1/files/revert/diff/${sessionId}`;
      const resp = await fetch(url, { headers: getAuthHeaders() });
      if (!resp.ok) {
        return;
      }
      const data = await resp.json();

      if (messageId) {
        setDiffs(data as ReviewFileDiff[]);
      } else {
        const allDiffs: ReviewFileDiff[] = [];
        for (const [msgId, msgDiffs] of Object.entries(data as Record<string, ReviewFileDiff[]>)) {
          allDiffs.push(...msgDiffs.map((d) => ({ ...d, _msgId: msgId })));
        }
        setDiffs(allDiffs);
      }
    } catch {
      // Silently handle
    } finally {
      setLoading(false);
    }
  }, [sessionId, messageId]);

  useEffect(() => {
    fetchDiffs();
  }, [fetchDiffs]);

  const filteredDiffs = useMemo(() => {
    const q = query.trim().toLowerCase();
    return diffs.filter((d) => {
      if (statusFilter !== 'all' && d.operation !== statusFilter) {
        return false;
      }
      if (q && !d.path.toLowerCase().includes(q)) {
        return false;
      }
      return true;
    });
  }, [diffs, query, statusFilter]);

  // Small lists render directly; virtualization only pays off for large change sets
  // and avoids measurement overhead (including jsdom) for the common case.
  const useVirtual = filteredDiffs.length > 30;
  const virtualizer = useVirtualizer({
    count: useVirtual ? filteredDiffs.length : 0,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 41,
    overscan: 8,
    measureElement: (el) => el.getBoundingClientRect().height,
  });
  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  // Filtering shrinks the list; reset scroll so the viewport never strands on empty space.
  useEffect(() => {
    const el = parentRef.current;
    if (el) {
      if (typeof el.scrollTo === 'function') {
        el.scrollTo({ top: 0 });
      } else {
        el.scrollTop = 0;
      }
    }
    if (useVirtual) {
      virtualizer.scrollToIndex(0, { align: 'start', behavior: 'auto' });
    }
  }, [query, statusFilter, useVirtual, virtualizer]);

  const toggleFile = useCallback((key: string) => {
    setExpandedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const toggleLongDiff = useCallback((key: string) => {
    setExpandedLongDiffs((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const handleCopyDiff = useCallback((content: string, key: string) => {
    navigator.clipboard.writeText(content);
    setCopiedFile(key);
    setTimeout(() => setCopiedFile(null), 2000);
  }, []);

  if (!sessionId) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        {t('selectSessionToReview')}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Tab Header & Workspace Path Badge */}
      <div className="flex items-center border-b border-border/50 px-2">
        <button
          onClick={() => setActiveTab('diff')}
          className={cn(
            'flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium transition-colors border-b-2',
            activeTab === 'diff'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground',
          )}
        >
          <FileEdit size={14} />
          {t('tabDiff', { count: diffs.length })}
        </button>
        <button
          onClick={() => setActiveTab('messages')}
          className={cn(
            'flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium transition-colors border-b-2',
            activeTab === 'messages'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground',
          )}
        >
          <MessagesSquare size={14} />
          {t('tabMessages')}
        </button>

        {workspacePath && (
          <span
            title={workspacePath}
            className="ml-2 hidden sm:inline-block font-mono text-[10px] text-muted-foreground bg-muted/60 px-2 py-0.5 rounded border border-border/40 truncate max-w-[160px]"
          >
            {formatPathForDisplay(workspacePath, 24)}
          </span>
        )}

        {activeTab === 'diff' && (
          <div className="ml-auto pr-1">
            <button
              onClick={fetchDiffs}
              disabled={loading}
              aria-label="Refresh diffs"
              className="p-1.5 rounded-full hover:bg-muted transition-colors text-muted-foreground"
            >
              <RefreshCw size={14} className={cn(loading && 'animate-spin')} />
            </button>
          </div>
        )}
      </div>

      {/* Diff toolbar: search + status filter */}
      {activeTab === 'diff' && diffs.length > 0 && (
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border/30">
          <div className="flex items-center gap-1.5 flex-1 min-w-0 bg-muted/50 border border-border/50 rounded-lg px-2 py-1">
            <Search size={13} className="text-muted-foreground shrink-0" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search files"
              aria-label="Search files"
              className="flex-1 min-w-0 bg-transparent text-xs focus:outline-none placeholder:text-muted-foreground"
            />
          </div>
          <div className="flex items-center gap-1 shrink-0" aria-label="Filter by status">
            {(['all', 'create', 'modify'] as StatusFilter[]).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setStatusFilter(s)}
                className={cn(
                  'px-2 py-1 rounded-md text-[11px] font-medium transition-colors',
                  statusFilter === s
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted',
                )}
              >
                {s === 'all' ? 'All' : s === 'create' ? 'A' : 'M'}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Tab Content */}
      <div className="flex-1 overflow-hidden flex flex-col min-h-0">
        {activeTab === 'diff' ? (
          <>
            {diffs.length === 0 && !loading && (
              <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
                {t('noChangesDetected')}
              </div>
            )}
            {diffs.length > 0 && filteredDiffs.length === 0 && !loading && (
              <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
                No files match your search.
              </div>
            )}
            <div ref={parentRef} className="flex-1 overflow-auto">
              {filteredDiffs.length > 0 &&
                (useVirtual ? (
                  <div style={{ height: `${totalSize}px`, position: 'relative' }}>
                    {virtualItems.map((row) => {
                      const diff = filteredDiffs[row.index];
                      if (!diff) {
                        return null;
                      }
                      return (
                        <div
                          key={row.key}
                          data-index={row.index}
                          ref={virtualizer.measureElement}
                          style={{
                            position: 'absolute',
                            top: 0,
                            left: 0,
                            width: '100%',
                            transform: `translateY(${row.start}px)`,
                          }}
                        >
                        <ReviewDiffRow
                          diff={diff}
                          rowKey={reviewRowKey(diff)}
                          expanded={expandedFiles.has(reviewRowKey(diff))}
                          longExpanded={expandedLongDiffs.has(reviewRowKey(diff))}
                          copied={copiedFile === reviewRowKey(diff)}
                          onToggle={toggleFile}
                          onToggleLong={toggleLongDiff}
                          onCopy={handleCopyDiff}
                        />
                      </div>
                    );
                  })}
                  </div>
                ) : (
                  <div>
                    {filteredDiffs.map((diff) => {
                      const key = reviewRowKey(diff);
                      return (
                        <ReviewDiffRow
                          key={key}
                          diff={diff}
                          rowKey={key}
                          expanded={expandedFiles.has(key)}
                          longExpanded={expandedLongDiffs.has(key)}
                          copied={copiedFile === key}
                          onToggle={toggleFile}
                          onToggleLong={toggleLongDiff}
                          onCopy={handleCopyDiff}
                        />
                      );
                    })}
                  </div>
                ))}
            </div>
            {filteredDiffs.length > 0 && (
              <div className="px-4 py-1.5 text-[11px] text-muted-foreground border-t border-border/30 flex items-center gap-1">
                <ChevronDown size={12} />
                Showing {filteredDiffs.length} of {diffs.length} files
              </div>
            )}
          </>
        ) : (
          <MessagePreview chatId={sessionId} />
        )}
      </div>

      {/* Feedback Input */}
      {onSendFeedback && sessionId && (
        <div className="border-t border-border/50 px-4 py-3">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value)}
              placeholder={t('feedbackPlaceholder')}
              className="flex-1 text-sm bg-muted/50 border border-border/50 rounded-lg px-3 py-1.5
                focus:outline-none focus:ring-1 focus:ring-primary/50"
              onKeyDown={(e) => {
                if (isImeComposing(e)) {
                  return;
                }
                if (e.key === 'Enter' && feedbackText.trim()) {
                  onSendFeedback(sessionId, feedbackText.trim());
                  setFeedbackText('');
                }
              }}
            />
            <button
              onClick={() => {
                if (feedbackText.trim()) {
                  onSendFeedback(sessionId, feedbackText.trim());
                  setFeedbackText('');
                }
              }}
              disabled={!feedbackText.trim()}
              className="p-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90
                disabled:opacity-40 transition-colors"
            >
              <MessageSquare size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
