'use client';

/**
 * Text views of the workspace file preview: the read-only code view and the editor, both with line numbers.
 *
 * [INPUT]
 * - content / label / onChange: what to show, what the editor is called for assistive technology, and where typing
 *   goes
 *
 * [OUTPUT]
 * - LineNumberedCode: read-only code view, one row per line; the numbers are drawn by `numbered-code.css`
 * - LineNumberedEditor: textarea editor whose line-number gutter follows its scrolling
 * - formatBytes: human-readable file size; empty when the size is unknown
 *
 * [POS]
 * Presentation pieces of WorkspaceFilePreview, kept apart from the editing state in useWorkspaceTextEditor.
 */

import React, { memo, useCallback, useMemo, useRef } from 'react';
import { cn } from '@/lib/utils/classnameUtils';

export function formatBytes(bytes: number | null): string {
  if (bytes === null) {
    return '';
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function countLines(text: string): number {
  let count = 1;
  for (let at = text.indexOf('\n'); at !== -1; at = text.indexOf('\n', at + 1)) {
    count += 1;
  }
  return count;
}

/**
 * Line numbers as one block of text. Gutter and text share one line height (`leading-5`), so number n sits beside
 * line n at any length, and a keystroke that adds or removes no line leaves the gutter untouched.
 */
const LineNumbers: React.FC<{ count: number; className: string; ref?: React.Ref<HTMLDivElement> }> = memo(
  ({ count, className, ref }) => {
    const numbers = useMemo(() => Array.from({ length: count }, (_, index) => index + 1).join('\n'), [count]);
    return (
      <div
        ref={ref}
        aria-hidden="true"
        className={`select-none whitespace-pre text-right pr-3 pl-2 text-muted-foreground/50 border-r border-border/30 shrink-0 bg-background ${className}`}
      >
        {numbers}
      </div>
    );
  },
);
LineNumbers.displayName = 'LineNumbers';

/** Past this many lines one element per line stops paying off: the file is then shown as plain text, unnumbered. */
const MAX_NUMBERED_ROWS = 100_000;

/**
 * Past this many rows laying out all of them takes about a frame or more when the panel is resized (measured: 2,000
 * rows re-lay out in 5 ms in Chromium and 17 ms in WebKit, 5,000 rows in 12 ms and 43 ms), so the browser may skip the
 * rows that are off screen. Below it every row is laid out and the scrollbar length stays exact.
 */
const LAZY_ROWS_FROM = 2_000;

/** The rows of a file: every line with the line break that ends it, so the rows read back exactly as the file. */
function splitRows(content: string): string[] {
  const lines = content.split('\n');
  const tail = lines.pop() ?? '';
  const rows = lines.map((line) => `${line}\n`);
  if (tail !== '' || rows.length === 0) {
    rows.push(tail);
  }
  return rows;
}

export const LineNumberedCode: React.FC<{ content: string }> = memo(({ content }) => {
  const rows = useMemo(() => splitRows(content), [content]);

  if (rows.length > MAX_NUMBERED_ROWS) {
    return (
      <pre className="px-3 text-xs font-mono leading-5 whitespace-pre-wrap break-words text-foreground">{content}</pre>
    );
  }
  return (
    <pre
      className={cn('numbered-code font-mono text-foreground', rows.length > LAZY_ROWS_FROM && 'numbered-code-lazy')}
      style={{ '--numbered-code-digits': String(rows.length).length } as React.CSSProperties}
    >
      {rows.map((row, index) => (
        // Rows have no identity beyond their position: the list is replaced as a whole when the file changes.
        <span key={index} className="numbered-code-line">
          {row}
        </span>
      ))}
    </pre>
  );
});
LineNumberedCode.displayName = 'LineNumberedCode';

export const LineNumberedEditor: React.FC<{
  content: string;
  /** What assistive technology announces for the textarea: the name of the file being edited. */
  label: string;
  onChange: (value: string) => void;
}> = memo(({ content, label, onChange }) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lineCountRef = useRef<HTMLDivElement>(null);

  const syncScroll = useCallback(() => {
    if (textareaRef.current && lineCountRef.current) {
      lineCountRef.current.scrollTop = textareaRef.current.scrollTop;
    }
  }, []);

  return (
    <div className="flex text-xs font-mono leading-5 h-full">
      {/* The horizontal track (nothing overflows, so it stays empty) takes the room of the textarea's own scrollbar:
          both then scroll to the same end and the last numbers stay level with the last lines. */}
      <LineNumbers ref={lineCountRef} count={countLines(content)} className="overflow-x-scroll overflow-y-hidden" />
      <textarea
        ref={textareaRef}
        aria-label={label}
        value={content}
        onChange={(e) => onChange(e.target.value)}
        onScroll={syncScroll}
        className="flex-1 pl-3 pr-3 bg-transparent text-foreground outline-none resize-none leading-5 whitespace-pre overflow-auto"
        spellCheck={false}
      />
    </div>
  );
});
LineNumberedEditor.displayName = 'LineNumberedEditor';
