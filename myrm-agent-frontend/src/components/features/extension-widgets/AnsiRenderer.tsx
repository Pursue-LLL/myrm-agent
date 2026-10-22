'use client';

/**
 * ANSI Escape Code Rich Color Renderer Component.
 *
 * [INPUT] raw: string, parseAnsiString
 * [OUTPUT] AnsiRenderer: Monospace terminal-style text container with fidelity color rendering.
 * [POS] src/components/features/extension-widgets/AnsiRenderer.tsx
 */

import { memo, useMemo } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { parseAnsiString } from './ansiParser';

export interface AnsiRendererProps {
  raw: string;
  className?: string;
  preClassName?: string;
}

export const AnsiRenderer = memo(function AnsiRenderer({
  raw,
  className,
  preClassName,
}: AnsiRendererProps) {
  const tokens = useMemo(() => {
    return parseAnsiString(raw);
  }, [raw]);

  if (!raw || tokens.length === 0) {
    return null;
  }

  return (
    <div
      className={cn(
        'rounded-lg bg-slate-950 p-2.5 text-slate-100 font-mono text-xs overflow-x-auto selection:bg-slate-700',
        className,
      )}
      data-testid="ansi-renderer-container"
    >
      <pre className={cn('whitespace-pre-wrap break-words m-0 leading-relaxed font-mono', preClassName)}>
        {tokens.map((token, idx) => {
          const style: React.CSSProperties = {};
          if (token.style.color) {
            style.color = token.style.color;
          }
          if (token.style.backgroundColor) {
            style.backgroundColor = token.style.backgroundColor;
          }
          if (token.style.fontWeight) {
            style.fontWeight = token.style.fontWeight;
          }
          if (token.style.fontStyle) {
            style.fontStyle = token.style.fontStyle;
          }
          if (token.style.textDecoration) {
            style.textDecoration = token.style.textDecoration;
          }
          if (token.style.opacity !== undefined) {
            style.opacity = token.style.opacity;
          }

          return (
            <span key={`${idx}-${token.text.slice(0, 8)}`} style={style}>
              {token.text}
            </span>
          );
        })}
      </pre>
    </div>
  );
});
