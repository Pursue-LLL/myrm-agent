'use client';

/**
 * Text views of the workspace file preview: the read-only code view and the editor, both with line numbers.
 *
 * [INPUT]
 * - content / language / label / onChange: what to show, how it is labelled, what the editor is called for
 *   assistive technology, and where typing goes
 *
 * [OUTPUT]
 * - LineNumberedCode: read-only code view
 * - LineNumberedEditor: textarea editor whose line-number gutter follows its scrolling
 * - getLanguage: language label of a file name (a `data-language` hint, not highlighting)
 * - formatBytes: human-readable file size; empty when the size is unknown
 *
 * [POS]
 * Presentation pieces of WorkspaceFilePreview, kept apart from the editing state in useWorkspaceTextEditor.
 */

import React, { memo, useCallback, useMemo, useRef } from 'react';

export function getLanguage(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const map: Record<string, string> = {
    py: 'python',
    js: 'javascript',
    ts: 'typescript',
    tsx: 'tsx',
    jsx: 'jsx',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    toml: 'toml',
    xml: 'xml',
    html: 'html',
    htm: 'html',
    css: 'css',
    scss: 'scss',
    less: 'less',
    md: 'markdown',
    sql: 'sql',
    sh: 'bash',
    bash: 'bash',
    zsh: 'bash',
    rs: 'rust',
    go: 'go',
    java: 'java',
    kt: 'kotlin',
    c: 'c',
    cpp: 'cpp',
    h: 'c',
    hpp: 'cpp',
    cs: 'csharp',
    rb: 'ruby',
    php: 'php',
    swift: 'swift',
    r: 'r',
    lua: 'lua',
    csv: 'csv',
    svg: 'xml',
  };
  return map[ext] || 'plaintext';
}

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

export const LineNumberedCode: React.FC<{ content: string; language: string }> = memo(({ content, language }) => (
  <div className="flex text-xs font-mono leading-5">
    <LineNumbers count={countLines(content)} className="sticky left-0" />
    <pre className="pl-3 pr-3 flex-1 whitespace-pre-wrap break-words text-foreground overflow-x-auto">
      <code data-language={language}>{content}</code>
    </pre>
  </div>
));
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
