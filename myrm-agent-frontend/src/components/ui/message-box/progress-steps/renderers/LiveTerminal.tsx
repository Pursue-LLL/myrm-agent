'use client';

import React, { useRef, useEffect } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';

import { getLineTone, TONE_CLASSES } from './lineToneUtils';

interface LiveTerminalProps {
  stdout?: string;
}

export const LiveTerminal: React.FC<LiveTerminalProps> = ({ stdout }) => {
  const containerRef = useRef<HTMLPreElement>(null);
  const workspaceDir = useChatStore((s) => s.workspaceDir);

  // Auto-scroll to bottom as new stdout chunks arrive
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [stdout]);

  if (!stdout) return null;

  // Regular expression to extract zero-copy WebP plotted image pointers
  // Pattern matches the Myrm proprietary APC sequence format
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
          // Dark background for terminal feel
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
            // Custom scrollbar
            'scrollbar-thin scrollbar-thumb-zinc-700 hover:scrollbar-thumb-zinc-600 scrollbar-track-transparent',
          )}
        >
          {stdout.split('\n').map((line, i) => {
            // Check if this line is an intercepted image pointer sequence
            imageSequenceRegex.lastIndex = 0;
            const match = imageSequenceRegex.exec(line);

            if (match) {
              const filepath = match[1];
              const columns = parseInt(match[2], 10);
              const rows = parseInt(match[3], 10);

              // Build our secure sandbox Vault Proxy rendering URL
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
      </div>
    </div>
  );
};
