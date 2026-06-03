'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { FileEdit, ChevronDown, ChevronRight, RefreshCw, MessageSquare, MessagesSquare, User, Bot } from 'lucide-react';
import { createPatch } from 'diff';
import { cn } from '@/lib/utils/classnameUtils';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import { getMessages } from '@/services/chat';
import type { Message } from '@/store/chat/types';

interface FileDiff {
  path: string;
  operation: string;
  original: string | null;
  current: string | null;
  isBinary: boolean;
}

interface ReviewPanelProps {
  sessionId: string | null;
  messageId?: string;
  onSendFeedback?: (chatId: string, feedback: string) => void;
}

type ReviewTab = 'diff' | 'messages';

function computeUnifiedDiff(original: string | null, current: string | null, path: string): string {
  return createPatch(path, original ?? '', current ?? '', '', '', { context: 3 });
}

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

export default function ReviewPanel({ sessionId, messageId, onSendFeedback }: ReviewPanelProps) {
  const t = useTranslations('multiPane');
  const [activeTab, setActiveTab] = useState<ReviewTab>('diff');
  const [diffs, setDiffs] = useState<FileDiff[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());
  const [feedbackText, setFeedbackText] = useState('');

  const fetchDiffs = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const url = messageId
        ? `${getBackendUrl()}/api/v1/files/revert/diff/${sessionId}/${messageId}`
        : `${getBackendUrl()}/api/v1/files/revert/diff/${sessionId}`;
      const resp = await fetch(url, { headers: getAuthHeaders() });
      if (!resp.ok) return;
      const data = await resp.json();

      if (messageId) {
        setDiffs(data as FileDiff[]);
      } else {
        const allDiffs: FileDiff[] = [];
        for (const msgDiffs of Object.values(data as Record<string, FileDiff[]>)) {
          allDiffs.push(...msgDiffs);
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

  const toggleFile = (path: string) => {
    setExpandedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  if (!sessionId) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        {t('selectSessionToReview')}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Tab Header */}
      <div className="flex items-center border-b border-border/50">
        <button
          onClick={() => setActiveTab('diff')}
          className={cn(
            'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2',
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
            'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2',
            activeTab === 'messages'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground',
          )}
        >
          <MessagesSquare size={14} />
          {t('tabMessages')}
        </button>
        {activeTab === 'diff' && (
          <div className="ml-auto pr-2">
            <button
              onClick={fetchDiffs}
              disabled={loading}
              className="p-1.5 rounded-full hover:bg-muted transition-colors text-muted-foreground"
            >
              <RefreshCw size={14} className={cn(loading && 'animate-spin')} />
            </button>
          </div>
        )}
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-auto">
        {activeTab === 'diff' ? (
          <>
            {diffs.length === 0 && !loading && (
              <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
                {t('noChangesDetected')}
              </div>
            )}
            {diffs.map((diff) => {
              const isExpanded = expandedFiles.has(diff.path);
              const fileName = diff.path.split('/').pop() || diff.path;

              return (
                <div key={diff.path} className="border-b border-border/30">
                  <button
                    onClick={() => toggleFile(diff.path)}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-muted/50 transition-colors"
                  >
                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    <span
                      className={cn(
                        'text-xs px-1.5 py-0.5 rounded font-mono',
                        diff.operation === 'create'
                          ? 'bg-green-500/10 text-green-600'
                          : 'bg-yellow-500/10 text-yellow-600',
                      )}
                    >
                      {diff.operation === 'create' ? 'A' : 'M'}
                    </span>
                    <span className="text-muted-foreground truncate">{diff.path.replace(fileName, '')}</span>
                    <span className="font-medium">{fileName}</span>
                  </button>

                  {isExpanded && !diff.isBinary && (
                    <div className="px-4 pb-3">
                      <pre className="text-xs font-mono bg-muted/30 rounded-lg p-3 overflow-x-auto max-h-[400px] overflow-y-auto">
                        {computeUnifiedDiff(diff.original, diff.current, diff.path)
                          .split('\n')
                          .map((line, i) => (
                            <div
                              key={i}
                              className={cn(
                                'px-1',
                                line.startsWith('+') &&
                                  !line.startsWith('+++') &&
                                  'bg-green-500/10 text-green-700 dark:text-green-400',
                                line.startsWith('-') &&
                                  !line.startsWith('---') &&
                                  'bg-red-500/10 text-red-700 dark:text-red-400',
                                line.startsWith('@@') && 'text-blue-500 font-semibold',
                              )}
                            >
                              {line}
                            </div>
                          ))}
                      </pre>
                    </div>
                  )}

                  {isExpanded && diff.isBinary && (
                    <div className="px-4 pb-3 text-xs text-muted-foreground italic">{t('binaryFileDiff')}</div>
                  )}
                </div>
              );
            })}
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
                if (e.nativeEvent.isComposing) return;
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
