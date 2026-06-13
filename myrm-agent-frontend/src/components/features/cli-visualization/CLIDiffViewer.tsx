/**
 * CLIDiffViewer - CLI Agent Diff 预览薄包装
 *
 * [INPUT]
 * - diff: unified diff 格式字符串
 * - filePath / onClose / defaultViewMode / className: 透传至 DiffViewer
 *
 * [OUTPUT]
 * - CLIDiffViewer: 带 shadow 样式的 Diff 预览（Tauri 桌面端使用）
 *
 * [POS]
 * CLI 可视化的 Diff 预览入口。核心逻辑委托 lib/diff/DiffViewer。
 * 仅在 Tauri 桌面环境使用。
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
