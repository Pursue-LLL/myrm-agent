/**
 * CLIDiffViewer - CLI Agent Diff 预览
 *
 * [INPUT]
 * - lib/diff/DiffViewer::DiffViewer (POS: 共享 Diff 可视化组件)
 *
 * [OUTPUT]
 * - CLIDiffViewer: 带阴影样式的 Diff 预览（Tauri 桌面端使用）
 * - CLIDiffViewerProps: 组件 Props 类型（等同 DiffViewerProps）
 *
 * [POS]
 * CLI 可视化的 Diff 预览入口。添加 `shadow-lg` 阴影后透传 DiffViewer。仅 Tauri 桌面环境使用。
 */

'use client';

import React, { memo } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { DiffViewer, type DiffViewerProps } from '@/lib/diff/DiffViewer';

export type CLIDiffViewerProps = DiffViewerProps;

export const CLIDiffViewer: React.FC<CLIDiffViewerProps> = memo((props) => (
  <DiffViewer {...props} className={cn('shadow-lg', props.className)} />
));

CLIDiffViewer.displayName = 'CLIDiffViewer';

export default CLIDiffViewer;
