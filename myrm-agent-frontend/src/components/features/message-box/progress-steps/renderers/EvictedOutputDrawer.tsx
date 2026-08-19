'use client';

import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { X, Copy, Check, Search, ChevronUp, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { getApiBaseUrl } from '@/lib/deploy-mode';
import { getLineTone, TONE_CLASSES } from './lineToneUtils';
import { formatStoredSize } from './sizeFormatUtils';

interface EvictedOutputDrawerProps {
  filename: string;
  chatId: string;
  onClose: () => void;
  storageTruncated?: boolean;
}

type LoadState = 'loading' | 'ready' | 'expired' | 'error';

const PAGE_SIZE = 500;

function isEvictedExpiredResponse(body: unknown): boolean {
  if (!body || typeof body !== 'object') {
    return false;
  }
  const record = body as Record<string, unknown>;
  if (record.expired === true) {
    return true;
  }
  const detail = record.detail;
  if (detail && typeof detail === 'object') {
    return (detail as { expired?: boolean }).expired === true;
  }
  return false;
}

function buildEvictedPageUrl(
  chatId: string,
  filename: string,
  offset: number,
  limit: number,
): string {
  const params = new URLSearchParams({
    chat_id: chatId,
    filename,
    offset: String(offset),
    limit: String(limit),
  });
  return `${getApiBaseUrl()}/files/evicted?${params.toString()}`;
}

const EvictedOutputDrawer: React.FC<EvictedOutputDrawerProps> = ({
  filename,
  chatId,
  onClose,
  storageTruncated: storageTruncatedProp,
}) => {
  const t = useTranslations('progressSteps.evictedOutput');
  const [pageContent, setPageContent] = useState('');
  const [totalLines, setTotalLines] = useState(0);
  const [storedChars, setStoredChars] = useState(0);
  const [storageTruncatedFromApi, setStorageTruncatedFromApi] = useState(false);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [pageLoading, setPageLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [searchVisible, setSearchVisible] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [currentMatchIdx, setCurrentMatchIdx] = useState(0);
  const contentRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const fetchControllerRef = useRef<AbortController | null>(null);

  const totalPages = Math.max(1, Math.ceil(totalLines / PAGE_SIZE));
  const pageOffset = (currentPage - 1) * PAGE_SIZE;

  const fetchPage = useCallback(
    async (page: number, initial: boolean) => {
      fetchControllerRef.current?.abort();
      const controller = new AbortController();
      fetchControllerRef.current = controller;

      if (initial) {
        setLoadState('loading');
      } else {
        setPageLoading(true);
      }

      try {
        const offset = (page - 1) * PAGE_SIZE;
        const url = buildEvictedPageUrl(chatId, filename, offset, PAGE_SIZE);
        const res = await fetch(url, { signal: controller.signal });

        if (!res.ok) {
          if (res.status === 404) {
            setLoadState('expired');
            return;
          }
          const body = await res.json().catch(() => null);
          if (isEvictedExpiredResponse(body)) {
            setLoadState('expired');
          } else {
            setLoadState('error');
          }
          return;
        }

        const data = (await res.json()) as {
          content?: string;
          total_lines?: number;
          stored_chars?: number;
          storage_truncated?: boolean;
        };

        setPageContent(data.content || '');
        if (typeof data.total_lines === 'number') {
          setTotalLines(data.total_lines);
        }
        if (typeof data.stored_chars === 'number') {
          setStoredChars(data.stored_chars);
        }
        if (data.storage_truncated === true) {
          setStorageTruncatedFromApi(true);
        }
        setLoadState('ready');
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setLoadState('error');
        }
      } finally {
        setPageLoading(false);
      }
    },
    [chatId, filename],
  );

  useEffect(() => {
    void fetchPage(currentPage, currentPage === 1);
    return () => fetchControllerRef.current?.abort();
  }, [currentPage, fetchPage]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (searchVisible) {
          setSearchVisible(false);
          setSearchTerm('');
        } else {
          onClose();
        }
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault();
        setSearchVisible(true);
        setTimeout(() => searchInputRef.current?.focus(), 50);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose, searchVisible]);

  const fetchAllContent = useCallback(async (): Promise<string> => {
    const parts: string[] = [];
    let offset = 0;
    let knownTotal = totalLines > 0 ? totalLines : PAGE_SIZE;

    while (offset < knownTotal) {
      const url = buildEvictedPageUrl(chatId, filename, offset, PAGE_SIZE);
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error('Failed to fetch evicted content');
      }
      const data = (await res.json()) as { content?: string; total_lines?: number };
      parts.push(data.content || '');
      if (typeof data.total_lines === 'number') {
        knownTotal = data.total_lines;
      }
      offset += PAGE_SIZE;
    }

    return parts.join('');
  }, [chatId, filename, totalLines]);

  const handleCopy = useCallback(async () => {
    try {
      const fullContent =
        totalPages <= 1 ? pageContent : await fetchAllContent();
      await navigator.clipboard.writeText(fullContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API may fail in insecure contexts
    }
  }, [fetchAllContent, pageContent, totalPages]);

  const lines = useMemo(() => pageContent.split('\n'), [pageContent]);

  const allMatchIndices = useMemo(() => {
    if (!searchTerm) {return [] as number[];}
    const lowerSearch = searchTerm.toLowerCase();
    const indices: number[] = [];
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].toLowerCase().includes(lowerSearch)) {
        indices.push(pageOffset + i);
      }
    }
    return indices;
  }, [searchTerm, lines, pageOffset]);

  const matchCount = allMatchIndices.length;

  const highlightMatches = useMemo(() => {
    if (!searchTerm) {return new Set<number>();}
    const matches = new Set<number>();
    for (const idx of allMatchIndices) {
      if (idx >= pageOffset && idx < pageOffset + lines.length) {
        matches.add(idx);
      }
    }
    return matches;
  }, [searchTerm, allMatchIndices, pageOffset, lines.length]);

  const renderInlineHighlight = useCallback(
    (line: string, isCurrent: boolean): React.ReactNode => {
      if (!searchTerm) {return line || ' ';}
      const parts: React.ReactNode[] = [];
      const lowerLine = line.toLowerCase();
      const lowerSearch = searchTerm.toLowerCase();
      let lastIdx = 0;
      let pos = lowerLine.indexOf(lowerSearch);
      while (pos !== -1) {
        if (pos > lastIdx) {parts.push(line.slice(lastIdx, pos));}
        parts.push(
          <mark
            key={pos}
            className={
              isCurrent
                ? 'bg-orange-400/50 text-orange-50 rounded-sm px-[1px]'
                : 'bg-yellow-400/30 text-yellow-50 rounded-sm px-[1px]'
            }
          >
            {line.slice(pos, pos + searchTerm.length)}
          </mark>,
        );
        lastIdx = pos + searchTerm.length;
        pos = lowerLine.indexOf(lowerSearch, lastIdx);
      }
      if (lastIdx < line.length) {parts.push(line.slice(lastIdx));}
      return parts.length > 0 ? <>{parts}</> : line || ' ';
    },
    [searchTerm],
  );

  const jumpToMatch = useCallback(
    (matchIdx: number) => {
      if (allMatchIndices.length === 0) {return;}
      const wrappedIdx =
        ((matchIdx % allMatchIndices.length) + allMatchIndices.length) %
        allMatchIndices.length;
      setCurrentMatchIdx(wrappedIdx);
      const lineIdx = allMatchIndices[wrappedIdx];
      const targetPage = Math.floor(lineIdx / PAGE_SIZE) + 1;
      if (targetPage !== currentPage) {
        setCurrentPage(targetPage);
      }
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          const el = contentRef.current?.querySelector(`[data-line="${lineIdx}"]`);
          el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
        });
      });
    },
    [allMatchIndices, currentPage],
  );

  useEffect(() => {
    if (allMatchIndices.length > 0) {
      jumpToMatch(0);
    } else {
      setCurrentMatchIdx(0);
    }
  }, [allMatchIndices, jumpToMatch]);

  const showStorageTruncated = storageTruncatedProp === true || storageTruncatedFromApi;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        data-testid="evicted-output-drawer"
        className={cn(
          'relative flex flex-col w-[min(90vw,100%)] sm:w-[90vw] max-w-5xl h-[min(80vh,100%)] sm:h-[80vh]',
          'bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden',
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 bg-zinc-900/60">
          <div className="flex items-center gap-3">
            <div className="flex space-x-1.5">
              <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
              <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
              <div className="w-2.5 h-2.5 rounded-full bg-green-500/80" />
            </div>
            <span className="text-xs font-medium text-zinc-400 truncate max-w-[50vw] sm:max-w-[300px]">{filename}</span>
            {loadState === 'ready' && totalLines > 0 && (
              <span className="text-[10px] text-zinc-600">
                {t('lineCount', { count: totalLines.toLocaleString() })}
                {storedChars > 0 ? ` · ${formatStoredSize(storedChars)}` : ''}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {loadState === 'ready' && (
              <>
                <button
                  onClick={() => {
                    setSearchVisible(!searchVisible);
                    if (!searchVisible) {setTimeout(() => searchInputRef.current?.focus(), 50);}
                  }}
                  className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
                  title={t('searchTitle')}
                >
                  <Search size={14} />
                </button>
                <button
                  onClick={handleCopy}
                  className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
                  title={t('copyAll')}
                >
                  {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              <X size={14} />
            </button>
          </div>
        </div>

        {showStorageTruncated && (
          <div
            data-testid="evicted-output-storage-truncated"
            className="px-4 py-2 border-b border-amber-500/20 bg-amber-500/5"
          >
            <span className="text-[11px] text-amber-500/90">{t('storageTruncated')}</span>
          </div>
        )}

        {/* Search bar */}
        {searchVisible && (
          <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-800/60 bg-zinc-900/40">
            <Search size={12} className="text-zinc-500" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  jumpToMatch(e.shiftKey ? currentMatchIdx - 1 : currentMatchIdx + 1);
                }
              }}
              placeholder={totalPages > 1 ? t('searchPagePlaceholder') : t('searchPlaceholder')}
              className="flex-1 bg-transparent text-xs text-zinc-300 placeholder-zinc-600 outline-none"
            />
            {searchTerm && (
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-zinc-500 tabular-nums">
                  {matchCount > 0 ? `${currentMatchIdx + 1}/${matchCount}` : '0/0'}
                </span>
                <button
                  onClick={() => jumpToMatch(currentMatchIdx - 1)}
                  disabled={matchCount === 0}
                  className="p-0.5 rounded text-zinc-500 hover:text-zinc-300 disabled:opacity-30"
                >
                  <ChevronUp size={12} />
                </button>
                <button
                  onClick={() => jumpToMatch(currentMatchIdx + 1)}
                  disabled={matchCount === 0}
                  className="p-0.5 rounded text-zinc-500 hover:text-zinc-300 disabled:opacity-30"
                >
                  <ChevronDown size={12} />
                </button>
              </div>
            )}
          </div>
        )}

        {/* Content */}
        <div ref={contentRef} className="flex-1 overflow-y-auto p-0 relative">
          {(loadState === 'loading' || pageLoading) && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-zinc-950/60">
              <div className="flex items-center gap-2 text-zinc-500 text-sm">
                <div className="w-4 h-4 border-2 border-zinc-600 border-t-zinc-300 rounded-full animate-spin" />
                {loadState === 'loading' ? t('loading') : t('loadingPage')}
              </div>
            </div>
          )}

          {loadState === 'expired' && (
            <div
              data-testid="evicted-output-expired"
              className="flex flex-col items-center justify-center h-full gap-3 text-zinc-500"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-zinc-600">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
              <p className="text-sm font-medium text-zinc-400">{t('expiredTitle')}</p>
              <p className="text-xs text-zinc-600 max-w-[300px] text-center">
                {t('expiredDesc')}
              </p>
            </div>
          )}

          {loadState === 'error' && (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-zinc-500">
              <p className="text-sm font-medium text-red-400">{t('errorTitle')}</p>
              <p className="text-xs text-zinc-600">{t('errorDesc')}</p>
            </div>
          )}

          {loadState === 'ready' && (
            <pre className="font-mono text-[12px] leading-[1.6] text-zinc-300 whitespace-pre-wrap break-words p-3">
              {lines.map((line, idx) => {
                const globalIdx = pageOffset + idx;
                const tone = getLineTone(line);
                const isMatch = highlightMatches.has(globalIdx);
                const isCurrentMatch = isMatch && allMatchIndices[currentMatchIdx] === globalIdx;

                return (
                  <div
                    key={globalIdx}
                    data-line={globalIdx}
                    className={cn(
                      'flex',
                      TONE_CLASSES[tone],
                      isCurrentMatch
                        ? 'bg-orange-500/20 border-l-2 border-orange-400'
                        : isMatch && 'bg-yellow-500/10 border-l-2 border-yellow-500/50',
                    )}
                  >
                    <span className="inline-block w-12 shrink-0 text-right pr-3 text-zinc-600 select-none text-[10px]">
                      {globalIdx + 1}
                    </span>
                    <span className="flex-1" style={{ wordBreak: 'break-word' }}>
                      {isMatch ? renderInlineHighlight(line, isCurrentMatch) : line || ' '}
                    </span>
                  </div>
                );
              })}
            </pre>
          )}
        </div>

        {/* Pagination footer */}
        {loadState === 'ready' && totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-2 border-t border-zinc-800/60 bg-zinc-900/40">
            <span className="text-[10px] text-zinc-600">
              {t('pageOf', { current: currentPage, total: totalPages })}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1 || pageLoading}
                className="px-2 py-0.5 rounded text-[10px] text-zinc-400 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {t('prev')}
              </button>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages || pageLoading}
                className="px-2 py-0.5 rounded text-[10px] text-zinc-400 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {t('next')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default EvictedOutputDrawer;
