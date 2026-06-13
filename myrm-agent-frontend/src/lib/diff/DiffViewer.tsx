/**
 * DiffViewer - 统一 Diff 可视化组件
 *
 * [INPUT]
 * - diff: unified diff 格式字符串
 * - filePath: 文件路径（可选，用于显示和语法高亮语言推断）
 * - onClose: 关闭回调
 * - defaultViewMode: 初始视图模式 (unified | split)
 * - className: 自定义类名
 *
 * [OUTPUT]
 * - DiffViewer: 通用 Diff 对比预览组件
 *   - 支持 Unified / Split 视图模式（真正的左右配对）
 *   - Prism 语法高亮
 *   - 新增/删除行数统计
 *
 * [POS]
 * lib/diff 层的共享 Diff 可视化组件。消除 InlineDiffViewer 与 CLIDiffViewer 的代码重复，
 * 由两者作为薄包装层引用。
 */

'use client';

import React, { memo, useState, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Copy, Check, SplitSquareHorizontal, AlignJustify, FileEdit, Plus, Minus } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Highlight, themes, Prism } from 'prism-react-renderer';
import { useTheme } from 'next-themes';
import { useDiffParser } from '@/hooks/useDiffParser';
import type { DiffLine, DiffHunk } from '@/lib/diff/parseUnifiedDiff';
import { CLIFileIcon } from '@/components/features/cli-visualization/CLIFileIcon';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

export interface DiffViewerProps {
  diff: string;
  filePath?: string;
  onClose?: () => void;
  defaultViewMode?: 'unified' | 'split';
  className?: string;
}

type ViewMode = 'unified' | 'split';

/** Split 视图的配对行 */
interface SplitPair {
  left: DiffLine | null;
  right: DiffLine | null;
}

const EXT_TO_LANGUAGE: Record<string, string> = {
  ts: 'typescript',
  tsx: 'tsx',
  js: 'javascript',
  jsx: 'jsx',
  py: 'python',
  rs: 'rust',
  go: 'go',
  java: 'java',
  kt: 'kotlin',
  rb: 'ruby',
  css: 'css',
  scss: 'scss',
  html: 'markup',
  xml: 'markup',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  md: 'markdown',
  sql: 'sql',
  sh: 'bash',
  bash: 'bash',
  zsh: 'bash',
  c: 'c',
  cpp: 'cpp',
  h: 'c',
  hpp: 'cpp',
  cs: 'csharp',
  swift: 'swift',
  toml: 'toml',
  lua: 'lua',
  r: 'r',
  php: 'php',
  dart: 'dart',
};

function inferLanguage(filePath: string): string {
  const ext = filePath.split('.').pop()?.toLowerCase() ?? '';
  const lang = EXT_TO_LANGUAGE[ext] ?? 'text';
  return Prism.languages[lang] ? lang : 'text';
}

/**
 * 将 hunk 的行列表转为 Split 配对数组。
 * 核心算法：连续的 deletion 与紧随其后的 addition 配对对齐，context 行左右同时显示。
 */
function buildSplitPairs(lines: DiffLine[]): SplitPair[] {
  const pairs: SplitPair[] = [];
  let i = 0;
  const filtered = lines.filter((l) => l.type !== 'header');

  while (i < filtered.length) {
    const line = filtered[i];

    if (line.type === 'context') {
      pairs.push({ left: line, right: line });
      i++;
      continue;
    }

    if (line.type === 'deletion') {
      const deletions: DiffLine[] = [];
      while (i < filtered.length && filtered[i].type === 'deletion') {
        deletions.push(filtered[i]);
        i++;
      }
      const additions: DiffLine[] = [];
      while (i < filtered.length && filtered[i].type === 'addition') {
        additions.push(filtered[i]);
        i++;
      }

      const maxLen = Math.max(deletions.length, additions.length);
      for (let j = 0; j < maxLen; j++) {
        pairs.push({
          left: j < deletions.length ? deletions[j] : null,
          right: j < additions.length ? additions[j] : null,
        });
      }
      continue;
    }

    if (line.type === 'addition') {
      pairs.push({ left: null, right: line });
      i++;
      continue;
    }

    i++;
  }

  return pairs;
}

// --------------- 行渲染子组件 ---------------

function getLineBackground(type: DiffLine['type']): string {
  switch (type) {
    case 'addition':
      return 'bg-green-500/10 dark:bg-green-500/20';
    case 'deletion':
      return 'bg-red-500/10 dark:bg-red-500/20';
    case 'header':
      return 'bg-blue-500/10 dark:bg-blue-500/20';
    default:
      return '';
  }
}

function getLineNumberStyle(type: DiffLine['type']): string {
  switch (type) {
    case 'addition':
      return 'text-green-600 dark:text-green-400';
    case 'deletion':
      return 'text-red-600 dark:text-red-400';
    default:
      return 'text-muted-foreground';
  }
}

function getLinePrefix(type: DiffLine['type']): string {
  switch (type) {
    case 'addition':
      return '+';
    case 'deletion':
      return '-';
    default:
      return ' ';
  }
}

/** 语法高亮单行内容 */
const HighlightedContent: React.FC<{
  content: string;
  language: string;
  prismTheme: typeof themes.oneLight;
}> = memo(({ content, language, prismTheme }) => {
  if (language === 'text' || !content.trim()) {
    return <code className="flex-1 py-0.5 pr-4 whitespace-pre overflow-x-auto">{content}</code>;
  }

  return (
    <Highlight theme={prismTheme} code={content} language={language}>
      {({ tokens, getTokenProps }) => (
        <code className="flex-1 py-0.5 pr-4 whitespace-pre overflow-x-auto">
          {tokens[0]?.map((token, k) => {
            const { key: _key, ...rest } = getTokenProps({ token, key: k });
            return <span key={k} {...rest} style={{ ...rest.style, backgroundColor: 'transparent' }} />;
          })}
        </code>
      )}
    </Highlight>
  );
});
HighlightedContent.displayName = 'HighlightedContent';

/** Unified 视图单行 */
const UnifiedDiffLine: React.FC<{
  line: DiffLine;
  language: string;
  prismTheme: typeof themes.oneLight;
}> = memo(({ line, language, prismTheme }) => {
  const bgClass = getLineBackground(line.type);
  const numClass = getLineNumberStyle(line.type);

  if (line.type === 'header') {
    return (
      <div className={cn('flex font-mono text-xs', bgClass)}>
        <span className="w-16 text-center py-0.5 text-blue-600 dark:text-blue-400 font-medium">{line.content}</span>
      </div>
    );
  }

  return (
    <div className={cn('flex font-mono text-xs hover:bg-muted/50', bgClass)}>
      <span className={cn('w-12 text-right pr-2 py-0.5 select-none border-r border-border/50', numClass)}>
        {line.oldLineNumber ?? ''}
      </span>
      <span className={cn('w-12 text-right pr-2 py-0.5 select-none border-r border-border/50', numClass)}>
        {line.newLineNumber ?? ''}
      </span>
      <span className={cn('w-6 text-center py-0.5 font-bold', numClass)}>{getLinePrefix(line.type)}</span>
      <HighlightedContent content={line.content} language={language} prismTheme={prismTheme} />
    </div>
  );
});
UnifiedDiffLine.displayName = 'UnifiedDiffLine';

/** Split 视图的半侧内容 */
const SplitHalf: React.FC<{
  line: DiffLine | null;
  side: 'left' | 'right';
  language: string;
  prismTheme: typeof themes.oneLight;
}> = memo(({ line, side, language, prismTheme }) => {
  const isDeletion = line?.type === 'deletion';
  const isAddition = line?.type === 'addition';
  const bgClass = isDeletion ? 'bg-red-500/10 dark:bg-red-500/20' : isAddition ? 'bg-green-500/10 dark:bg-green-500/20' : '';
  const numClass = isDeletion
    ? 'text-red-600 dark:text-red-400'
    : isAddition
      ? 'text-green-600 dark:text-green-400'
      : 'text-muted-foreground';
  const lineNumber = side === 'left' ? line?.oldLineNumber : line?.newLineNumber;

  return (
    <div className={cn('flex-1 flex', side === 'left' ? 'border-r border-border' : '', bgClass)}>
      <span className={cn('w-12 text-right pr-2 py-0.5 select-none border-r border-border/50', numClass)}>
        {lineNumber ?? ''}
      </span>
      {line ? (
        <HighlightedContent content={line.content} language={language} prismTheme={prismTheme} />
      ) : (
        <code className="flex-1 py-0.5 px-2">&nbsp;</code>
      )}
    </div>
  );
});
SplitHalf.displayName = 'SplitHalf';

/** Split 视图配对行 */
const SplitDiffLine: React.FC<{
  pair: SplitPair;
  language: string;
  prismTheme: typeof themes.oneLight;
}> = memo(({ pair, language, prismTheme }) => (
  <div className="flex font-mono text-xs">
    <SplitHalf line={pair.left} side="left" language={language} prismTheme={prismTheme} />
    <SplitHalf line={pair.right} side="right" language={language} prismTheme={prismTheme} />
  </div>
));
SplitDiffLine.displayName = 'SplitDiffLine';

/** Hunk 内容渲染 */
const HunkContent: React.FC<{
  hunk: DiffHunk;
  viewMode: ViewMode;
  language: string;
  prismTheme: typeof themes.oneLight;
}> = memo(({ hunk, viewMode, language, prismTheme }) => {
  const splitPairs = useMemo(() => (viewMode === 'split' ? buildSplitPairs(hunk.lines) : []), [hunk.lines, viewMode]);

  if (viewMode === 'unified') {
    return (
      <>
        {hunk.lines.map((line, i) => (
          <UnifiedDiffLine key={i} line={line} language={language} prismTheme={prismTheme} />
        ))}
      </>
    );
  }

  return (
    <>
      {splitPairs.map((pair, i) => (
        <SplitDiffLine key={i} pair={pair} language={language} prismTheme={prismTheme} />
      ))}
    </>
  );
});
HunkContent.displayName = 'HunkContent';

// --------------- 主组件 ---------------

export const DiffViewer: React.FC<DiffViewerProps> = memo(
  ({ diff, filePath, onClose, defaultViewMode = 'unified', className }) => {
    const [viewMode, setViewMode] = useState<ViewMode>(defaultViewMode);
    const [copied, setCopied] = useState(false);
    const { theme } = useTheme();

    const parsed = useDiffParser(diff);
    const displayPath = filePath || parsed.filePath || 'Unknown file';
    const language = useMemo(() => inferLanguage(displayPath), [displayPath]);

    const prismTheme = useMemo(() => {
      return theme === 'dark' ? themes.oneDark : themes.oneLight;
    }, [theme]);

    const handleCopy = useCallback(async () => {
      try {
        await writeToClipboard(diff);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch {
        console.error('Failed to copy diff');
      }
    }, [diff]);

    const toggleViewMode = useCallback(() => {
      setViewMode((prev) => (prev === 'unified' ? 'split' : 'unified'));
    }, []);

    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 10 }}
        className={cn('bg-background border border-border rounded-lg overflow-hidden', className)}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2 bg-muted/50 border-b border-border">
          <div className="flex items-center gap-2">
            <FileEdit className="h-4 w-4 text-orange-500" />
            <CLIFileIcon filename={displayPath} className="h-4 w-4" />
            <span className="text-sm font-medium truncate max-w-[300px]" title={displayPath}>
              {displayPath.split('/').pop()}
            </span>
            <div className="flex items-center gap-2 ml-2 text-xs">
              <span className="flex items-center gap-1 text-green-600 dark:text-green-400">
                <Plus className="h-3 w-3" />
                {parsed.additions}
              </span>
              <span className="flex items-center gap-1 text-red-600 dark:text-red-400">
                <Minus className="h-3 w-3" />
                {parsed.deletions}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={toggleViewMode}
              className="p-1.5 rounded hover:bg-muted transition-colors"
              title={viewMode === 'unified' ? 'Split view' : 'Unified view'}
            >
              {viewMode === 'unified' ? (
                <SplitSquareHorizontal className="h-4 w-4" />
              ) : (
                <AlignJustify className="h-4 w-4" />
              )}
            </button>
            <button onClick={handleCopy} className="p-1.5 rounded hover:bg-muted transition-colors" title="Copy diff">
              {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
            </button>
            {onClose && (
              <button onClick={onClose} className="p-1.5 rounded hover:bg-muted transition-colors" title="Close">
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        <div className="max-h-[400px] overflow-auto">
          {parsed.isBinary ? (
            <div className="p-4 text-center text-muted-foreground">Binary file changed</div>
          ) : parsed.hunks.length === 0 ? (
            <div className="p-4 text-center text-muted-foreground">No changes</div>
          ) : (
            <AnimatePresence mode="wait">
              <motion.div
                key={viewMode}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
              >
                {parsed.hunks.map((hunk, i) => (
                  <HunkContent key={i} hunk={hunk} viewMode={viewMode} language={language} prismTheme={prismTheme} />
                ))}
              </motion.div>
            </AnimatePresence>
          )}
        </div>
      </motion.div>
    );
  },
);

DiffViewer.displayName = 'DiffViewer';

export default DiffViewer;
