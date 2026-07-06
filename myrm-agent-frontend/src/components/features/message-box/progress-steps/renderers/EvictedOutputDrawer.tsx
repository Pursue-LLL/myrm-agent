'use client';

import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { X, Copy, Check, Search, ChevronUp, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { getLineTone, TONE_CLASSES } from './lineToneUtils';

interface EvictedOutputDrawerProps {
  filename: string;
  chatId: string;
  onClose: () => void;
}

type LoadState = 'loading' | 'ready' | 'expired' | 'error';

const PAGE_SIZE = 500;

const EvictedOutputDrawer: React.FC<EvictedOutputDrawerProps> = ({ filename, chatId, onClose }) => {
  const [content, setContent] = useState('');
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [copied, setCopied] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [searchVisible, setSearchVisible] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [currentMatchIdx, setCurrentMatchIdx] = useState(0);
  const contentRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    const fetchContent = async () => {
      try {
        const baseUrl = process.env.NEXT_PUBLIC_API_URL || '';
        const url = `${baseUrl}/api/v1/files/evicted?chat_id=${encodeURIComponent(chatId)}&filename=${encodeURIComponent(filename)}`;
        const res = await fetch(url, { signal: controller.signal });

        if (!res.ok) {
          const body = await res.json().catch(() => null);
          if (body?.expired) {
            setLoadState('expired');
          } else {
            setLoadState('error');
          }
          return;
        }

        const data = await res.json();
        setContent(data.content || '');
        setLoadState('ready');
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setLoadState('error');
        }
      }
    };

    fetchContent();
    return () => controller.abort();
  }, [filename, chatId]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault();
        setSearchVisible(true);
        setTimeout(() => searchInputRef.current?.focus(), 50);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API may fail in insecure contexts
    }
  }, [content]);

  const lines = useMemo(() => content.split('\n'), [content]);
  const totalPages = Math.ceil(lines.length / PAGE_SIZE);

  const visibleLines = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return lines.slice(start, start + PAGE_SIZE);
  }, [lines, currentPage]);

  const allMatchIndices = useMemo(() => {
    if (!searchTerm) return [] as number[];
    const lowerSearch = searchTerm.toLowerCase();
    const indices: number[] = [];
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].toLowerCase().includes(lowerSearch)) {
        indices.push(i);
      }
    }
    return indices;
  }, [searchTerm, lines]);

  const matchCount = allMatchIndices.length;

  const highlightMatches = useMemo(() => {
    if (!searchTerm) return new Set<number>();
    const matches = new Set<number>();
    const start = (currentPage - 1) * PAGE_SIZE;
    const end = start + PAGE_SIZE;
    for (const idx of allMatchIndices) {
      if (idx >= start && idx < end) matches.add(idx);
    }
    return matches;
  }, [searchTerm, allMatchIndices, currentPage]);

  const jumpToMatch = useCallback(
    (matchIdx: number) => {
      if (allMatchIndices.length === 0) return;
      const wrappedIdx = ((matchIdx % allMatchIndices.length) + allMatchIndices.length) % allMatchIndices.length;
      setCurrentMatchIdx(wrappedIdx);
      const lineIdx = allMatchIndices[wrappedIdx];
      const targetPage = Math.floor(lineIdx / PAGE_SIZE) + 1;
      setCurrentPage(targetPage);
      // Double rAF ensures DOM has re-rendered after page change before scrolling
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          const el = contentRef.current?.querySelector(`[data-line="${lineIdx}"]`);
          el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
        });
      });
    },
    [allMatchIndices],
  );

  useEffect(() => {
    if (allMatchIndices.length > 0) {
      jumpToMatch(0);
    } else {
      setCurrentMatchIdx(0);
    }
  }, [allMatchIndices, jumpToMatch]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className={cn(
          'relative flex flex-col w-[90vw] max-w-5xl h-[80vh]',
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
            <span className="text-xs font-medium text-zinc-400 truncate max-w-[300px]">{filename}</span>
            {loadState === 'ready' && (
              <span className="text-[10px] text-zinc-600">{lines.length.toLocaleString()} lines</span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {loadState === 'ready' && (
              <>
                <button
                  onClick={() => {
                    setSearchVisible(!searchVisible);
                    if (!searchVisible) setTimeout(() => searchInputRef.current?.focus(), 50);
                  }}
                  className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
                  title="Search (Ctrl+F)"
                >
                  <Search size={14} />
                </button>
                <button
                  onClick={handleCopy}
                  className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
                  title="Copy all"
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
              placeholder="Search..."
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
        <div ref={contentRef} className="flex-1 overflow-y-auto p-0">
          {loadState === 'loading' && (
            <div className="flex items-center justify-center h-full">
              <div className="flex items-center gap-2 text-zinc-500 text-sm">
                <div className="w-4 h-4 border-2 border-zinc-600 border-t-zinc-300 rounded-full animate-spin" />
                Loading full output...
              </div>
            </div>
          )}

          {loadState === 'expired' && (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-500">
              <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-zinc-600">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
              <p className="text-sm font-medium text-zinc-400">Output Expired</p>
              <p className="text-xs text-zinc-600 max-w-[300px] text-center">
                This output file has been cleaned up. Evicted outputs are retained for the session duration only.
              </p>
            </div>
          )}

          {loadState === 'error' && (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-zinc-500">
              <p className="text-sm font-medium text-red-400">Failed to load output</p>
              <p className="text-xs text-zinc-600">Please try again later.</p>
            </div>
          )}

          {loadState === 'ready' && (
            <pre className="font-mono text-[12px] leading-[1.6] text-zinc-300 whitespace-pre-wrap break-words p-3">
              {visibleLines.map((line, idx) => {
                const globalIdx = (currentPage - 1) * PAGE_SIZE + idx;
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
                      {line || ' '}
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
              Page {currentPage} of {totalPages}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-2 py-0.5 rounded text-[10px] text-zinc-400 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Prev
              </button>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="px-2 py-0.5 rounded text-[10px] text-zinc-400 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default EvictedOutputDrawer;
