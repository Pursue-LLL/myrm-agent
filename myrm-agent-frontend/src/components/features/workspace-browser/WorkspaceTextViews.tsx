'use client';

/**
 * Text views of the workspace file preview: the read-only code view and the editor, both with line numbers.
 *
 * [INPUT]
 * - content / language / onChange: what to show, how it is labelled, and where typing goes
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

import React, { memo, useCallback, useRef } from 'react';

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

export const LineNumberedCode: React.FC<{ content: string; language: string }> = memo(({ content, language }) => {
  const lines = content.split('\n');

  return (
    <div className="flex text-xs font-mono leading-relaxed">
      <div className="select-none text-right pr-3 pl-2 text-muted-foreground/50 border-r border-border/30 shrink-0 sticky left-0 bg-background">
        {lines.map((_, i) => (
          <div key={i} className="h-5">
            {i + 1}
          </div>
        ))}
      </div>
      <pre className="pl-3 pr-3 flex-1 whitespace-pre-wrap break-words text-foreground overflow-x-auto">
        <code data-language={language}>{content}</code>
      </pre>
    </div>
  );
});
LineNumberedCode.displayName = 'LineNumberedCode';

export const LineNumberedEditor: React.FC<{
  content: string;
  onChange: (value: string) => void;
}> = memo(({ content, onChange }) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lineCountRef = useRef<HTMLDivElement>(null);
  const lines = content.split('\n');

  const syncScroll = useCallback(() => {
    if (textareaRef.current && lineCountRef.current) {
      lineCountRef.current.scrollTop = textareaRef.current.scrollTop;
    }
  }, []);

  return (
    <div className="flex text-xs font-mono leading-relaxed h-full">
      <div
        ref={lineCountRef}
        className="select-none text-right pr-3 pl-2 text-muted-foreground/50 border-r border-border/30 shrink-0 overflow-hidden bg-background"
      >
        {lines.map((_, i) => (
          <div key={i} className="h-5">
            {i + 1}
          </div>
        ))}
      </div>
      <textarea
        ref={textareaRef}
        value={content}
        onChange={(e) => onChange(e.target.value)}
        onScroll={syncScroll}
        className="flex-1 pl-3 pr-3 bg-transparent text-foreground outline-none resize-none leading-relaxed whitespace-pre overflow-auto"
        spellCheck={false}
      />
    </div>
  );
});
LineNumberedEditor.displayName = 'LineNumberedEditor';
