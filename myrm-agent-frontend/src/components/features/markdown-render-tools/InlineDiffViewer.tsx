/**
 * InlineDiffViewer - Markdown 内联 Diff 预览
 *
 * [INPUT]
 * - lib/diff/DiffViewer::DiffViewer (POS: 共享 Diff 可视化组件)
 *
 * [OUTPUT]
 * - InlineDiffViewer: 带 Markdown 消息气泡外边距的 Diff 预览
 * - InlineDiffViewerProps: 组件 Props 类型（等同 DiffViewerProps）
 *
 * [POS]
 * Markdown 渲染层的 Diff 预览入口。添加 `my-6` 外边距后透传 DiffViewer。
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
