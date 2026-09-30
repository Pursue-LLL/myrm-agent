'use client';

/**
 * @orphan-ok Verified exact anchor indexing visual capsule strip for compaction context
 *
 * [INPUT]
 * - anchors: ExactAnchorData containing commit SHAs, file paths, errors, symbols, and endpoints
 * - onSymbolClick?: Optional callback when clicking a file path or code symbol
 *
 * [OUTPUT]
 * - CompactionAnchorStrip: Glassmorphic interactive anchor capsule strip
 *
 * [POS]
 * Visual container for deterministic machine symbols extracted during context compaction.
 * Provides high-contrast, dual-theme glassmorphism, zero-emoji Lucide iconography,
 * and one-click clipboard copying.
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { GitCommit, FileCode, Code2, Network, AlertTriangle, ChevronDown, ChevronUp, Copy, Check } from 'lucide-react';

export interface ExactAnchorData {
  commitShas?: string[];
  filePaths?: string[];
  errorSpans?: string[];
  codeSymbols?: string[];
  apiEndpoints?: string[];
}

export interface CompactionAnchorStripProps {
  anchors: ExactAnchorData;
  className?: string;
  onSymbolClick?: (symbol: string, category: keyof ExactAnchorData) => void;
}

export function CompactionAnchorStrip({ anchors, className = '', onSymbolClick }: CompactionAnchorStripProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copyTimerRef.current) {
        clearTimeout(copyTimerRef.current);
      }
    };
  }, []);

  const { commitShas = [], filePaths = [], errorSpans = [], codeSymbols = [], apiEndpoints = [] } = anchors;

  const totalCount =
    commitShas.length + filePaths.length + errorSpans.length + codeSymbols.length + apiEndpoints.length;

  const handleCopy = useCallback((text: string, id: string) => {
    navigator.clipboard?.writeText(text);
    setCopiedKey(id);
    if (copyTimerRef.current) {
      clearTimeout(copyTimerRef.current);
    }
    copyTimerRef.current = setTimeout(() => {
      setCopiedKey((current) => (current === id ? null : current));
    }, 1800);
  }, []);

  if (totalCount === 0) {
    return null;
  }

  return (
    <div
      data-testid="compaction-anchor-strip"
      className={`relative overflow-hidden rounded-xl border border-zinc-200/80 bg-white/70 p-3 shadow-sm backdrop-blur-md transition-all duration-200 hover:border-primary/40 hover:shadow-md dark:border-zinc-800/80 dark:bg-zinc-900/70 ${className}`}
    >
      {/* Header bar */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Code2 className="h-3.5 w-3.5" />
          </div>
          <span className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">Verified Anchors</span>
          <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
            {totalCount} symbols
          </span>
        </div>

        <button
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
          aria-expanded={isExpanded}
          aria-label={isExpanded ? 'Collapse anchors' : 'Expand anchors'}
        >
          <span>{isExpanded ? 'Collapse' : 'Inspect'}</span>
          {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </button>
      </div>

      {/* Summary preview badge line when collapsed */}
      {!isExpanded && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 pt-1">
          {commitShas.slice(0, 2).map((sha) => (
            <span
              key={sha}
              className="inline-flex items-center gap-1 rounded bg-zinc-100/80 px-1.5 py-0.5 font-mono text-[10px] text-zinc-700 dark:bg-zinc-800/80 dark:text-zinc-300"
            >
              <GitCommit className="h-2.5 w-2.5 text-zinc-500" />
              {sha.slice(0, 7)}
            </span>
          ))}
          {filePaths.slice(0, 2).map((path) => (
            <span
              key={path}
              className="inline-flex max-w-[130px] items-center gap-1 rounded bg-zinc-100/80 px-1.5 py-0.5 font-mono text-[10px] text-zinc-700 dark:bg-zinc-800/80 dark:text-zinc-300"
            >
              <FileCode className="h-2.5 w-2.5 shrink-0 text-zinc-500" />
              <span className="truncate">{path.split('/').pop()}</span>
            </span>
          ))}
          {codeSymbols.slice(0, 2).map((sym) => (
            <span
              key={sym}
              className="inline-flex max-w-[110px] items-center gap-1 rounded bg-zinc-100/80 px-1.5 py-0.5 font-mono text-[10px] text-zinc-700 dark:bg-zinc-800/80 dark:text-zinc-300"
            >
              <Code2 className="h-2.5 w-2.5 shrink-0 text-zinc-500" />
              <span className="truncate">{sym}</span>
            </span>
          ))}
          {totalCount > 6 && <span className="text-[10px] text-zinc-400">+{totalCount - 6} more</span>}
        </div>
      )}

      {/* Detailed symbol lists when expanded */}
      {isExpanded && (
        <div className="mt-3 space-y-2.5 border-t border-zinc-200/60 pt-2.5 text-xs dark:border-zinc-800/60">
          {/* Commits */}
          {commitShas.length > 0 && (
            <div className="space-y-1">
              <div className="flex items-center gap-1.5 text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
                <GitCommit className="h-3 w-3" />
                <span>Commits ({commitShas.length})</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {commitShas.map((sha) => {
                  const id = `sha-${sha}`;
                  const isCopied = copiedKey === id;
                  return (
                    <button
                      key={sha}
                      type="button"
                      onClick={() => handleCopy(sha, id)}
                      className="group inline-flex items-center gap-1 rounded-md border border-zinc-200/80 bg-zinc-50/50 px-2 py-0.5 font-mono text-[10px] text-zinc-700 transition-colors hover:border-primary/50 hover:bg-white dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-300 dark:hover:bg-zinc-800"
                      title="Click to copy SHA"
                    >
                      <span>{sha.slice(0, 8)}</span>
                      {isCopied ? (
                        <Check className="h-2.5 w-2.5 text-emerald-500" />
                      ) : (
                        <Copy className="h-2.5 w-2.5 opacity-40 group-hover:opacity-100" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Files */}
          {filePaths.length > 0 && (
            <div className="space-y-1">
              <div className="flex items-center gap-1.5 text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
                <FileCode className="h-3 w-3" />
                <span>Files ({filePaths.length})</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {filePaths.map((path) => {
                  const id = `path-${path}`;
                  const isCopied = copiedKey === id;
                  return (
                    <button
                      key={path}
                      type="button"
                      onClick={() => {
                        handleCopy(path, id);
                        onSymbolClick?.(path, 'filePaths');
                      }}
                      className="group inline-flex max-w-full sm:max-w-md items-center gap-1 rounded-md border border-zinc-200/80 bg-zinc-50/50 px-2 py-0.5 font-mono text-[10px] text-zinc-700 transition-colors hover:border-primary/50 hover:bg-white dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-300 dark:hover:bg-zinc-800"
                      title="Click to copy path"
                      aria-label={`Copy path: ${path}`}
                    >
                      <span className="truncate" title={path}>
                        {path}
                      </span>
                      {isCopied ? (
                        <Check className="h-2.5 w-2.5 shrink-0 text-emerald-500" />
                      ) : (
                        <Copy className="h-2.5 w-2.5 shrink-0 opacity-40 group-hover:opacity-100" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Code Symbols */}
          {codeSymbols.length > 0 && (
            <div className="space-y-1">
              <div className="flex items-center gap-1.5 text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
                <Code2 className="h-3 w-3" />
                <span>Symbols ({codeSymbols.length})</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {codeSymbols.map((sym) => {
                  const id = `sym-${sym}`;
                  const isCopied = copiedKey === id;
                  return (
                    <button
                      key={sym}
                      type="button"
                      onClick={() => {
                        handleCopy(sym, id);
                        onSymbolClick?.(sym, 'codeSymbols');
                      }}
                      className="group inline-flex max-w-full sm:max-w-xs items-center gap-1 rounded-md border border-zinc-200/80 bg-zinc-50/50 px-2 py-0.5 font-mono text-[10px] text-zinc-700 transition-colors hover:border-primary/50 hover:bg-white dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-300 dark:hover:bg-zinc-800"
                      title="Click to copy symbol"
                      aria-label={`Copy symbol: ${sym}`}
                    >
                      <span className="truncate" title={sym}>
                        {sym}
                      </span>
                      {isCopied ? (
                        <Check className="h-2.5 w-2.5 shrink-0 text-emerald-500" />
                      ) : (
                        <Copy className="h-2.5 w-2.5 shrink-0 opacity-40 group-hover:opacity-100" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* API Endpoints */}
          {apiEndpoints.length > 0 && (
            <div className="space-y-1">
              <div className="flex items-center gap-1.5 text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
                <Network className="h-3 w-3" />
                <span>Endpoints ({apiEndpoints.length})</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {apiEndpoints.map((ep) => {
                  const id = `ep-${ep}`;
                  const isCopied = copiedKey === id;
                  return (
                    <button
                      key={ep}
                      type="button"
                      onClick={() => handleCopy(ep, id)}
                      className="group inline-flex max-w-full sm:max-w-sm items-center gap-1 rounded-md border border-zinc-200/80 bg-zinc-50/50 px-2 py-0.5 font-mono text-[10px] text-zinc-700 transition-colors hover:border-primary/50 hover:bg-white dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-300 dark:hover:bg-zinc-800"
                      title="Click to copy endpoint"
                      aria-label={`Copy endpoint: ${ep}`}
                    >
                      <span className="truncate" title={ep}>
                        {ep}
                      </span>
                      {isCopied ? (
                        <Check className="h-2.5 w-2.5 shrink-0 text-emerald-500" />
                      ) : (
                        <Copy className="h-2.5 w-2.5 shrink-0 opacity-40 group-hover:opacity-100" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Errors */}
          {errorSpans.length > 0 && (
            <div className="space-y-1">
              <div className="flex items-center gap-1.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
                <AlertTriangle className="h-3 w-3" />
                <span>Error Signatures ({errorSpans.length})</span>
              </div>
              <div className="space-y-1">
                {errorSpans.map((err, i) => (
                  <div
                    key={`err-${i}`}
                    className="break-all whitespace-pre-wrap rounded-md border border-amber-200/60 bg-amber-50/40 p-2 font-mono text-[10px] text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200"
                  >
                    {err}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default CompactionAnchorStrip;
