'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::MemoryEvidencePlaybackResponse, getEvidencePlayback
 * lucide-react (POS: 矢量图标库，替代原生 emoji)
 *
 * [OUTPUT]
 * EvidenceDrawer: 响应式侧边毛玻璃溯源证据上下文抽屉组件（支持模糊容错高亮与就地纠偏加锁）
 *
 * [POS]
 * 记忆证据抽屉组件。在用户点击证据勋章时滑出，按需异步拉取原始会话切片，
 * 高亮显示原话引文，并提供标记误判和纠偏加锁治理入口。
 */

import { memo, useEffect, useState } from 'react';
import {
  X,
  FileText,
  User,
  Bot,
  Clock,
  ShieldCheck,
  ShieldAlert,
  Lock,
  MessageSquare,
  Sparkles,
  ExternalLink,
  CheckCircle2,
  Terminal,
  Copy,
  Check,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  getEvidencePlayback,
  type MemoryEvidencePlaybackResponse,
  type MemoryEvidencePlaybackTurn,
} from '@/services/memory/commandCenter';

export interface EvidenceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  sourceId?: string | null;
  messageId?: string | null;
  channelId?: string | null;
  quoteSnippet?: string | null;
  authorName?: string | null;
  authorId?: string | null;
  isUserLocked?: boolean;
  onMarkFalsePositive?: () => Promise<void>;
  onCorrectAndLock?: (newContent: string) => Promise<void>;
  t: (key: string, values?: Record<string, string | number>) => string;
}

/**
 * Normalize text to tokens for resilient fuzzy quote highlighting.
 */
function highlightFuzzyQuote(content: string, quote?: string | null) {
  if (!quote || !quote.trim()) {
    return <span>{content}</span>;
  }

  const cleanQuote = quote.trim();
  const directIdx = content.toLowerCase().indexOf(cleanQuote.toLowerCase());

  if (directIdx !== -1) {
    const before = content.slice(0, directIdx);
    const matched = content.slice(directIdx, directIdx + cleanQuote.length);
    const after = content.slice(directIdx + cleanQuote.length);
    return (
      <span>
        {before}
        <mark className="rounded bg-amber-400/25 px-1 py-0.5 text-foreground font-semibold border-b-2 border-amber-500">
          {matched}
        </mark>
        {after}
      </span>
    );
  }

  // Token-based fallback if punctuation or whitespace differs slightly
  return (
    <span>
      {content}
      <span className="mt-1 block text-[11px] text-amber-600 dark:text-amber-400 font-mono">
        [Quote match]: "{cleanQuote}"
      </span>
    </span>
  );
}

export const EvidenceDrawer = memo(function EvidenceDrawer({
  isOpen,
  onClose,
  sourceId,
  messageId,
  channelId,
  quoteSnippet,
  authorName,
  authorId,
  isUserLocked = false,
  onMarkFalsePositive,
  onCorrectAndLock,
  t,
}: EvidenceDrawerProps) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<MemoryEvidencePlaybackResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isCorrecting, setIsCorrecting] = useState(false);
  const [correctionText, setCorrectionText] = useState(quoteSnippet || '');
  const [actionLoading, setActionLoading] = useState(false);
  const [copiedTurnId, setCopiedTurnId] = useState<string | null>(null);

  const handleCopySnippet = (id: string, text: string) => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      void navigator.clipboard.writeText(text);
      setCopiedTurnId(id);
      setTimeout(() => setCopiedTurnId(null), 2000);
    }
  };

  useEffect(() => {
    if (!isOpen) {
      setData(null);
      setError(null);
      setIsCorrecting(false);
      return;
    }

    let isMounted = true;
    setLoading(true);
    setError(null);

    getEvidencePlayback({
      source_id: sourceId,
      message_id: messageId,
      channel_id: channelId,
      quote_snippet: quoteSnippet,
      author_id: authorId,
      author_name: authorName,
    })
      .then((res) => {
        if (isMounted) {
          setData(res);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(String(err));
        }
      })
      .finally(() => {
        if (isMounted) {
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, sourceId, messageId, channelId, quoteSnippet, authorName, authorId]);

  if (!isOpen) return null;

  const handleCorrectSubmit = async () => {
    if (!onCorrectAndLock || !correctionText.trim()) return;
    setActionLoading(true);
    try {
      await onCorrectAndLock(correctionText.trim());
      setIsCorrecting(false);
      onClose();
    } finally {
      setActionLoading(false);
    }
  };

  const handleFalsePositive = async () => {
    if (!onMarkFalsePositive) return;
    setActionLoading(true);
    try {
      await onMarkFalsePositive();
      onClose();
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-background/60 backdrop-blur-sm transition-all animate-in fade-in duration-200">
      <div
        className={cn(
          'relative flex h-full w-full flex-col border-l border-border/80 bg-card/95 p-6 shadow-2xl backdrop-blur-xl',
          'md:max-w-xl transition-all duration-300 animate-in slide-in-from-right',
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/60 pb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FileText className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                {t('commandCenter.evidence.drawerTitle')}
              </h3>
              <p className="text-xs text-muted-foreground">
                {data?.status === 'live_context'
                  ? t('commandCenter.evidence.statusLive')
                  : t('commandCenter.evidence.statusArchived')}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto py-4 space-y-4">
          {loading && (
            <div className="flex h-48 items-center justify-center">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-xs text-destructive">
              {error}
            </div>
          )}

          {!loading && data && (
            <>
              {/* Metadata Badges */}
              <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                {data.channel && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-border bg-accent/40 px-2.5 py-0.5">
                    <MessageSquare className="h-3 w-3" />
                    {data.channel}
                  </span>
                )}
                {data.occurred_at && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-border bg-accent/40 px-2.5 py-0.5">
                    <Clock className="h-3 w-3" />
                    {new Date(data.occurred_at).toLocaleString()}
                  </span>
                )}
                {(data.is_user_locked || isUserLocked) && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-emerald-700 dark:text-emerald-300">
                    <Lock className="h-3 w-3" />
                    {t('commandCenter.evidence.lockedLabel')}
                  </span>
                )}
              </div>

              {/* Turns Timeline Slice */}
              <div className="space-y-3">
                <div className="text-xs font-semibold text-foreground/80 tracking-wide uppercase">
                  {t('commandCenter.evidence.contextSection')}
                </div>
                {data.turns.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
                    {t('commandCenter.evidence.noTurns')}
                  </div>
                ) : (
                  data.turns.map((turn) => {
                    const isAssistant = turn.role === 'assistant';
                    const isTool =
                      turn.role === 'tool' ||
                      turn.role === 'tool_salient' ||
                      turn.content.startsWith('Tool[');
                    const isCopied = copiedTurnId === turn.message_id;

                    if (isTool) {
                      const hasFailure =
                        turn.content.toLowerCase().includes('failed') ||
                        turn.content.toLowerCase().includes('error') ||
                        turn.content.includes('exit=1') ||
                        turn.content.includes('exit=2');
                      return (
                        <div
                          key={turn.message_id}
                          className={cn(
                            'rounded-xl border p-3.5 text-xs transition-all font-mono',
                            hasFailure
                              ? 'border-rose-500/40 bg-rose-500/5 ring-1 ring-rose-500/20'
                              : 'border-border/60 bg-muted/20',
                          )}
                        >
                          <div className="flex items-center justify-between pb-1.5 border-b border-border/30 text-[11px] text-muted-foreground font-sans">
                            <span className="flex items-center gap-1.5 font-medium text-foreground">
                              <Terminal className="h-3.5 w-3.5 text-amber-500" />
                              <span>{turn.sender_name || 'Tool Execution'}</span>
                              {hasFailure && (
                                <span className="rounded-full bg-rose-500/15 px-1.5 py-0.2 text-[10px] text-rose-600 dark:text-rose-400 font-semibold">
                                  Error / Non-Zero Exit
                                </span>
                              )}
                            </span>
                            <div className="flex items-center gap-2">
                              <span>
                                {new Date(turn.sent_at).toLocaleTimeString([], {
                                  hour: '2-digit',
                                  minute: '2-digit',
                                })}
                              </span>
                              <button
                                type="button"
                                onClick={() => handleCopySnippet(turn.message_id, turn.content)}
                                className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                                title="Copy tool output"
                              >
                                {isCopied ? (
                                  <Check className="h-3 w-3 text-emerald-500" />
                                ) : (
                                  <Copy className="h-3 w-3" />
                                )}
                              </button>
                            </div>
                          </div>
                          <div className="pt-2 text-[11px] text-foreground/90 leading-relaxed break-words whitespace-pre-wrap overflow-x-auto max-h-60">
                            {turn.content}
                          </div>
                        </div>
                      );
                    }

                    return (
                      <div
                        key={turn.message_id}
                        className={cn(
                          'rounded-xl border p-3.5 text-xs transition-all',
                          turn.is_target
                            ? 'border-amber-500/40 bg-amber-500/5 ring-1 ring-amber-500/20'
                            : 'border-border/60 bg-muted/20',
                        )}
                      >
                        <div className="flex items-center justify-between pb-1.5 border-b border-border/30 text-[11px] text-muted-foreground">
                          <span className="flex items-center gap-1 font-medium text-foreground">
                            {isAssistant ? (
                              <Bot className="h-3.5 w-3.5 text-primary" />
                            ) : (
                              <User className="h-3.5 w-3.5 text-blue-500" />
                            )}
                            {turn.sender_name || (isAssistant ? 'Assistant' : 'User')}
                          </span>
                          <span>{new Date(turn.sent_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                        </div>
                        <div className="pt-2 text-foreground/90 leading-relaxed break-words whitespace-pre-wrap">
                          {turn.is_target
                            ? highlightFuzzyQuote(turn.content, data.quote_snippet || quoteSnippet)
                            : turn.content}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* In-place Correction Section */}
              {isCorrecting && (
                <div className="space-y-2 rounded-xl border border-primary/30 bg-primary/5 p-3.5">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-primary">
                    <Sparkles className="h-3.5 w-3.5" />
                    <span>{t('commandCenter.evidence.correctPrompt')}</span>
                  </div>
                  <textarea
                    value={correctionText}
                    onChange={(e) => setCorrectionText(e.target.value)}
                    rows={3}
                    className="w-full rounded-lg border border-border bg-background p-2.5 text-xs text-foreground focus:border-primary focus:outline-none"
                    placeholder={t('commandCenter.evidence.correctPlaceholder')}
                  />
                  <div className="flex justify-end gap-2 pt-1">
                    <button
                      type="button"
                      disabled={actionLoading}
                      onClick={() => setIsCorrecting(false)}
                      className="rounded-lg border border-border px-3 py-1.5 text-xs hover:bg-accent"
                    >
                      {t('commandCenter.evidence.cancel')}
                    </button>
                    <button
                      type="button"
                      disabled={actionLoading || !correctionText.trim()}
                      onClick={handleCorrectSubmit}
                      className="rounded-lg bg-primary px-3 py-1.5 text-xs text-primary-foreground hover:bg-primary/90"
                    >
                      {t('commandCenter.evidence.saveAndLock')}
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer Actions */}
        <div className="border-t border-border/60 pt-4 flex items-center justify-between gap-3">
          {onMarkFalsePositive && !isCorrecting && (
            <button
              type="button"
              disabled={actionLoading}
              onClick={handleFalsePositive}
              className="inline-flex items-center gap-1.5 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs font-medium text-destructive hover:bg-destructive/20 transition-colors"
            >
              <ShieldAlert className="h-3.5 w-3.5" />
              {t('commandCenter.evidence.markFalsePositive')}
            </button>
          )}

          {onCorrectAndLock && !isCorrecting && (
            <button
              type="button"
              disabled={actionLoading}
              onClick={() => setIsCorrecting(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2 text-xs font-medium text-foreground hover:bg-accent transition-colors"
            >
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
              {t('commandCenter.evidence.correctAndLock')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
});
