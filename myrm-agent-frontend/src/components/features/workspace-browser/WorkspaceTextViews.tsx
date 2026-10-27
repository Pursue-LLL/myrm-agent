'use client';

/**
 * Text views of the workspace file preview: the read-only code view and the editor, both with line numbers.
 *
 * [INPUT]
 * - content / language / label / onChange: what to show, the Prism grammar to colour it with, what the editor is
 *   called for assistive technology, and where typing goes
 * - lib/syntax/prism::resolveLanguage (POS: the one place that knows which grammars are registered and which texts are
 *   too risky to colour)
 * - lib/syntax/theme::syntaxThemeFor (POS: the colours of the current appearance, each readable at 4.5:1)
 *
 * [OUTPUT]
 * - LineNumberedCode: read-only code view, one row per line; coloured with Prism when its language has a grammar, no
 *   line is past `MAX_HIGHLIGHT_LINE_CHARS` (`lib/syntax/prism`) and the file is within MAX_HIGHLIGHTED_ROWS, _CHARS
 *   and _TOKENS; the numbers are drawn by `numbered-code.css`
 * - LineNumberedEditor: textarea editor whose line-number gutter follows its scrolling
 * - formatBytes: human-readable file size; empty when the size is unknown
 *
 * [POS]
 * Presentation pieces of WorkspaceFilePreview, kept apart from the editing state in useWorkspaceTextEditor.
 */

import { useTheme } from 'next-themes';
import { Highlight } from 'prism-react-renderer';
import React, { memo, useCallback, useMemo, useRef } from 'react';
import { resolveLanguage } from '@/lib/syntax/prism';
import { syntaxThemeFor } from '@/lib/syntax/theme';
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
        className={`select-none whitespace-pre text-right pr-3 pl-2 text-muted-foreground border-r border-border/30 shrink-0 bg-background ${className}`}
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

/**
 * Colouring adds an element per token, and what it costs follows the tokens, not the rows: 2,000 rows of code (about
 * 12,500 tokens) take 87 ms to render in Chromium (plain: 7 ms; 379 ms against 35 ms on a 4x slower CPU), while 100,000
 * characters of dense text (`a,a,a,`) make 100,000 elements and take 550 ms (2.4 s at 4x). So a file is coloured only
 * within all three limits, and past any of them it opens plain: the rows keep the lazy-rendering threshold, the
 * characters keep Prism from reading a megabyte of minified code, and the tokens bound the elements that reach the page
 * (tokenizing 100,000 characters takes 8 to 27 ms, so that last check costs little). One more guard lives in
 * `resolveLanguage`: a line longer than MAX_HIGHLIGHT_LINE_CHARS (a data URI, a minified bundle) keeps the whole file
 * plain, because a few grammars take seconds on such a line.
 */
const MAX_HIGHLIGHTED_ROWS = LAZY_ROWS_FROM;
const MAX_HIGHLIGHTED_CHARS = 100_000;
const MAX_HIGHLIGHTED_TOKENS = 20_000;

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

const PlainRow: React.FC<{ row: string }> = ({ row }) => <span className="numbered-code-line">{row}</span>;

/** Rows have no identity beyond their position: the list is replaced as a whole when the file changes. */
const PlainRows: React.FC<{ rows: string[] }> = ({ rows }) =>
  rows.map((row, index) => <PlainRow key={index} row={row} />);

/** What may follow a row's text in the file: its line break (CRLF included), or nothing on the last row. */
const ROW_END = /^\r?\n?$/;

/**
 * The rows coloured by Prism, which reads the whole file so a comment or string that spans lines keeps its colour on
 * every row. Prism's lines and the rows are two splits of the same text, so a row takes its colours only while the
 * tokens of its line spell exactly the row's text (the line break aside); any other row stays plain, which keeps the
 * text a copy yields identical to the file. A file with more tokens than MAX_HIGHLIGHTED_TOKENS stays plain as a whole.
 */
const HighlightedRows: React.FC<{ content: string; rows: string[]; language: string }> = ({
  content,
  rows,
  language,
}) => {
  const { resolvedTheme } = useTheme();
  return (
    <Highlight theme={syntaxThemeFor(resolvedTheme)} code={content} language={language}>
      {({ tokens, getTokenProps }) => {
        if (tokens.reduce((count, line) => count + line.length, 0) > MAX_HIGHLIGHTED_TOKENS) {
          return <PlainRows rows={rows} />;
        }
        return rows.map((row, index) => {
          const pieces = (tokens[index] ?? []).map((token) => ({ token, text: token.content.replace(/\n$/, '') }));
          const spelled = pieces.map((piece) => piece.text).join('');
          const ending = row.startsWith(spelled) ? row.slice(spelled.length) : null;
          if (ending === null || !ROW_END.test(ending)) {
            return <PlainRow key={index} row={row} />;
          }
          return (
            <span key={index} className="numbered-code-line">
              {pieces.map(({ token, text }, position) => {
                const { className, style } = getTokenProps({ token });
                return text === '' ? null : (
                  <span key={position} className={className} style={style}>
                    {text}
                  </span>
                );
              })}
              {ending}
            </span>
          );
        });
      }}
    </Highlight>
  );
};

export const LineNumberedCode: React.FC<{ content: string; language?: string }> = memo(({ content, language }) => {
  const rows = useMemo(() => splitRows(content), [content]);
  const grammar =
    rows.length <= MAX_HIGHLIGHTED_ROWS && content.length <= MAX_HIGHLIGHTED_CHARS
      ? resolveLanguage(language, content)
      : 'text';

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
      {grammar !== 'text' ? (
        <HighlightedRows content={content} rows={rows} language={grammar} />
      ) : (
        <PlainRows rows={rows} />
      )}
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
