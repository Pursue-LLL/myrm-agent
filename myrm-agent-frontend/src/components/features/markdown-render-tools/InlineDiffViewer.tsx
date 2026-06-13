/**
 * InlineDiffViewer - Markdown 内联 Diff 预览薄包装
 *
 * [INPUT]
 * - diff: unified diff 格式字符串
 * - filePath / onClose / defaultViewMode / className: 透传至 DiffViewer
 *
 * [OUTPUT]
 * - InlineDiffViewer: 带消息气泡外边距样式的 Diff 预览
 *
 * [POS]
 * Markdown 渲染层的 Diff 预览入口。核心逻辑委托 lib/diff/DiffViewer。
 */

'use client';

import React, { memo } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { DiffViewer, type DiffViewerProps } from '@/lib/diff/DiffViewer';

export type InlineDiffViewerProps = DiffViewerProps;

export const InlineDiffViewer: React.FC<InlineDiffViewerProps> = memo((props) => (
  <DiffViewer {...props} className={cn('my-6', props.className)} />
));

InlineDiffViewer.displayName = 'InlineDiffViewer';

export default InlineDiffViewer;
