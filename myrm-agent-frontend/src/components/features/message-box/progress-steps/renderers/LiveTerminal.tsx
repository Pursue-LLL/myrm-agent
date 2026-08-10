'use client';

import React, { useRef, useEffect, useState, lazy, Suspense } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';

import { getLineTone, TONE_CLASSES } from './lineToneUtils';
import { formatStoredSize } from './sizeFormatUtils';

const EvictedOutputDrawer = lazy(() => import('./EvictedOutputDrawer'));

interface LiveTerminalProps {
  stdout?: string;
  evictedFileRef?: string;
  evictedStoredChars?: number;
  evictedTotalLines?: number;
  evictedStorageTruncated?: boolean;
  evictedStderrFileRef?: string;
  evictedStderrStoredChars?: number;
  evictedStderrTotalLines?: number;
  evictedStderrStorageTruncated?: boolean;
}

export const LiveTerminal: React.FC<LiveTerminalProps> = ({
  stdout,
  evictedFileRef,
  evictedStoredChars,
  evictedTotalLines,
  evictedStorageTruncated,
  evictedStderrFileRef,
  evictedStderrStoredChars,
  evictedStderrTotalLines,
  evictedStderrStorageTruncated,
}) => {
  const t = useTranslations('progressSteps.evictedOutput');
  const containerRef = useRef<HTMLPreElement>(null);
  const workspaceDir = useChatStore((s) => s.workspaceDir);
  const chatId = useChatStore((s) => s.chatId);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [stderrDrawerOpen, setStderrDrawerOpen] = useState(false);

  const evictedBadge = evictedFileRef && (evictedTotalLines || evictedStoredChars)
    ? t('sizeBadge', {
        lines: (evictedTotalLines ?? 0).toLocaleString(),
        size: evictedStoredChars ? formatStoredSize(evictedStoredChars) : '—',
      })
    : null;

  const evictedStderrBadge =
    evictedStderrFileRef && (evictedStderrTotalLines || evictedStderrStoredChars)
      ? t('sizeBadge', {
          lines: (evictedStderrTotalLines ?? 0).toLocaleString(),
          size: evictedStderrStoredChars ? formatStoredSize(evictedStderrStoredChars) : '—',
        })
      : null;

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [stdout]);

  if (!stdout && !evictedFileRef && !evictedStderrFileRef) return null;

  const evictedFooter = evictedFileRef ? (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-1.5 px-3 py-1.5 border-t border-zinc-800/80 bg-zinc-900/30">
      <div className="flex flex-col sm:items-end gap-0.5 min-w-0">
        {evictedBadge && (
          <span className="text-[10px] text-zinc-500 tabular-nums truncate">{evictedBadge}</span>
        )}
        {evictedStorageTruncated && (
          <span className="text-[10px] text-amber-500/80">{t('storageTruncated')}</span>
        )}
      </div>
      <button
        data-testid="evicted-view-full-output"
        onClick={() => setDrawerOpen(true)}
        className={cn(
          'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium shrink-0',
          'bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 hover:text-blue-300',
          'border border-blue-500/20 transition-colors duration-150',
        )}
      >
        {stdout ? (
          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
        ) : null}
        {t('viewFull')}
      </button>
    </div>
  ) : null;

  const stderrFooter = evictedStderrFileRef ? (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-1.5 px-3 py-1.5 border-t border-zinc-800/80 bg-zinc-900/30">
      <div className="flex flex-col sm:items-end gap-0.5 min-w-0">
        {evictedStderrBadge && (
          <span className="text-[10px] text-zinc-500 tabular-nums truncate">{evictedStderrBadge}</span>
        )}
        {evictedStderrStorageTruncated && (
          <span className="text-[10px] text-amber-500/80">{t('storageTruncated')}</span>
        )}
      </div>
      <button
        data-testid="evicted-view-full-stderr-output"
        onClick={() => setStderrDrawerOpen(true)}
        className={cn(
          'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium shrink-0',
          'bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 hover:text-amber-300',
          'border border-amber-500/20 transition-colors duration-150',
        )}
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
        </svg>
        {t('viewFullStderr')}
      </button>
    </div>
  ) : null;

  if (!stdout && (evictedFileRef || evictedStderrFileRef)) {
    return (
      <div className="relative mt-2">
        <div
          className={cn(
            'flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 rounded-xl px-3 py-2',
            'bg-zinc-950/80 border border-zinc-800/80',
          )}
        >
          <div className="flex flex-col gap-1 min-w-0">
            {evictedFileRef ? (
              <>
                <span className="text-[11px] text-zinc-400">{t('savedHint')}</span>
                {evictedBadge && (
                  <span className="text-[10px] text-zinc-500 tabular-nums">{evictedBadge}</span>
                )}
                {evictedStorageTruncated && (
                  <span className="text-[10px] text-amber-500/80">{t('storageTruncated')}</span>
                )}
              </>
            ) : null}
            {evictedStderrFileRef ? (
              <>
                <span className="text-[11px] text-zinc-400">{t('savedStderrHint')}</span>
                {evictedStderrBadge && (
                  <span className="text-[10px] text-zinc-500 tabular-nums">{evictedStderrBadge}</span>
                )}
                {evictedStderrStorageTruncated && (
                  <span className="text-[10px] text-amber-500/80">{t('storageTruncated')}</span>
                )}
              </>
            ) : null}
          </div>
          <div className="flex items-center gap-1.5">
            {evictedFileRef ? (
              <button
                data-testid="evicted-view-full-output"
                onClick={() => setDrawerOpen(true)}
                className={cn(
                  'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium shrink-0',
                  'bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 hover:text-blue-300',
                  'border border-blue-500/20 transition-colors duration-150',
                )}
              >
                {t('viewFull')}
              </button>
            ) : null}
            {evictedStderrFileRef ? (
              <button
                data-testid="evicted-view-full-stderr-output"
                onClick={() => setStderrDrawerOpen(true)}
                className={cn(
                  'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium shrink-0',
                  'bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 hover:text-amber-300',
                  'border border-amber-500/20 transition-colors duration-150',
                )}
              >
                {t('viewFullStderr')}
              </button>
            ) : null}
          </div>
        </div>
        {evictedFileRef && drawerOpen && (
          <Suspense fallback={null}>
            <EvictedOutputDrawer
              filename={evictedFileRef}
              chatId={chatId || ''}
              onClose={() => setDrawerOpen(false)}
            />
          </Suspense>
        )}
        {evictedStderrFileRef && stderrDrawerOpen && (
          <Suspense fallback={null}>
            <EvictedOutputDrawer
              filename={evictedStderrFileRef}
              chatId={chatId || ''}
              onClose={() => setStderrDrawerOpen(false)}
            />
          </Suspense>
        )}
      </div>
    );
  }

  if (!stdout) return null;

  const escapeSequence = '\\u001b';
  const imageSequenceRegex = new RegExp(
    `${escapeSequence}_MyrmImage:vault://([^,]+),w=(\\d+),h=(\\d+)${escapeSequence}\\\\`,
    'g',
  );

  return (
    <div className="relative mt-2">
      <div
        className={cn(
          'relative rounded-xl overflow-hidden',
          'bg-zinc-950 dark:bg-[#0a0a0a]',
          'border border-zinc-800 dark:border-zinc-800/50',
          'shadow-inner',
        )}
      >
        <div className="flex items-center px-3 py-1.5 border-b border-zinc-800/80 bg-zinc-900/50">
          <div className="flex space-x-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-green-500/80" />
          </div>
          <span className="ml-3 text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Terminal</span>
        </div>

        <pre
          ref={containerRef}
          className={cn(
            'p-3 overflow-y-auto max-h-[400px]',
            'font-mono text-[12px] leading-relaxed text-zinc-300',
            'whitespace-pre-wrap break-words',
            'scrollbar-thin scrollbar-thumb-zinc-700 hover:scrollbar-thumb-zinc-600 scrollbar-track-transparent',
          )}
        >
          {stdout.split('\n').map((line, i) => {
            imageSequenceRegex.lastIndex = 0;
            const match = imageSequenceRegex.exec(line);

            if (match) {
              const filepath = match[1];
              const columns = parseInt(match[2], 10);
              const rows = parseInt(match[3], 10);

              const baseUrl = process.env.NEXT_PUBLIC_API_URL || '';
              const proxyUrl = `/api/v1/files/vault/render?filepath=${encodeURIComponent(filepath)}&workspace=${encodeURIComponent(workspaceDir || '')}`;
              const imageUrl = baseUrl ? `${baseUrl}${proxyUrl}` : proxyUrl;

              return (
                <div key={i} className="my-3 flex flex-col items-start gap-1">
                  <div className="relative rounded-lg overflow-hidden border border-zinc-800 bg-zinc-900/40 p-1 group">
                    <img
                      src={imageUrl}
                      alt="Sandbox Plot Artifact"
                      className="max-w-full h-auto rounded object-contain max-h-[350px] transition-transform duration-200 hover:scale-[1.02]"
                    />
                    <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-zinc-950/80 text-[10px] text-zinc-400 px-2 py-0.5 rounded border border-zinc-800">
                      {columns}x{rows} - WebP Rendered
                    </div>
                  </div>
                </div>
              );
            }

            const leadingSpacesMatch = line.match(/^ */);
            const leadingSpaces = leadingSpacesMatch ? leadingSpacesMatch[0].length : 0;
            const paddingLeft = leadingSpaces * 0.5;
            const tone = getLineTone(line);

            return (
              <div
                key={i}
                className={TONE_CLASSES[tone]}
                style={{
                  paddingLeft: `${paddingLeft}rem`,
                  textIndent: `-${paddingLeft}rem`,
                  wordBreak: 'break-word',
                }}
              >
                {line || ' '}
              </div>
            );
          })}
        </pre>

        {evictedFooter}
        {stderrFooter}
      </div>

      {evictedFileRef && drawerOpen && (
        <Suspense fallback={null}>
          <EvictedOutputDrawer
            filename={evictedFileRef}
            chatId={chatId || ''}
            onClose={() => setDrawerOpen(false)}
          />
        </Suspense>
      )}
      {evictedStderrFileRef && stderrDrawerOpen && (
        <Suspense fallback={null}>
          <EvictedOutputDrawer
            filename={evictedStderrFileRef}
            chatId={chatId || ''}
            onClose={() => setStderrDrawerOpen(false)}
          />
        </Suspense>
      )}
    </div>
  );
};
