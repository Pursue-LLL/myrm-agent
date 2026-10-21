'use client';

/**
 * [INPUT] diff::createPatch (POS: 文本 diff 生成); lib/diff/DiffViewer (POS: unified diff 可视化)
 * [OUTPUT] TextDiffViewer: old/new 纯文本对比内联组件
 * [POS] lib/diff 层文本 diff 薄包装，供配置冲突与技能进化等场景嵌入对话框/卡片。
 */

import { memo, useMemo } from 'react';
import { createPatch } from 'diff';
import { DiffViewer, type DiffViewerProps } from '@/lib/diff/DiffViewer';

export interface TextDiffViewerProps {
  oldValue: string;
  newValue: string;
  filePath?: string;
  defaultViewMode?: DiffViewerProps['defaultViewMode'];
  className?: string;
  maxHeight?: string | number;
}

export const TextDiffViewer = memo<TextDiffViewerProps>(
  ({ oldValue, newValue, filePath = 'content.txt', defaultViewMode = 'unified', className, maxHeight }) => {
    const diff = useMemo(
      () => createPatch(filePath, oldValue, newValue, '', '', { context: 3 }),
      [filePath, oldValue, newValue],
    );

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
