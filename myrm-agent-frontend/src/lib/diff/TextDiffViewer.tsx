'use client';

/**
 * [INPUT] diff::createPatch (POS: 文本 diff 生成，带耗时上限); lib/diff/DiffViewer (POS: unified diff 可视化)
 * [OUTPUT] TextDiffViewer: old/new 纯文本对比内联组件；改动大到来不及对比时只说明两侧行数
 * [POS] lib/diff 层文本 diff 薄包装，供配置冲突、技能进化与工作区文件审查嵌入对话框/卡片/面板。
 */

import { memo, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { createPatch } from 'diff';
import { cn } from '@/lib/utils/classnameUtils';
import { DiffViewer, type DiffViewerProps } from '@/lib/diff/DiffViewer';

/**
 * Finding the shortest edit script runs on the main thread and costs more the more two texts differ: a rewrite of a
 * few thousand lines can take seconds. Past this budget the comparison is abandoned instead of freezing the page.
 */
const DIFF_BUDGET_MS = 500;

export interface TextDiffViewerProps {
  oldValue: string;
  newValue: string;
  filePath?: string;
  defaultViewMode?: DiffViewerProps['defaultViewMode'];
  className?: string;
  maxHeight?: string | number;
}

/** Lines as a person counts them: the break that ends the last line does not start another one. */
function countLines(text: string): number {
  if (text === '') {
    return 0;
  }
  return text.split('\n').length - (text.endsWith('\n') ? 1 : 0);
}

export const TextDiffViewer = memo<TextDiffViewerProps>(
  ({ oldValue, newValue, filePath = 'content.txt', defaultViewMode = 'unified', className, maxHeight }) => {
    const t = useTranslations('common');
    const diff = useMemo(
      () => createPatch(filePath, oldValue, newValue, '', '', { context: 3, timeout: DIFF_BUDGET_MS }),
      [filePath, oldValue, newValue],
    );

    if (diff === undefined) {
      return (
        <output
          className={cn(
            'block rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground',
            className,
          )}
        >
          {t('diffTooLarge', { oldLines: countLines(oldValue), newLines: countLines(newValue) })}
        </output>
      );
    }

    return (
      <DiffViewer
        diff={diff}
        filePath={filePath}
        defaultViewMode={defaultViewMode}
        embedded
        className={className}
        maxHeight={maxHeight}
      />
    );
  },
);

TextDiffViewer.displayName = 'TextDiffViewer';

export default TextDiffViewer;
