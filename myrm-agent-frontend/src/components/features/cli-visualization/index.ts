/**
 * CLI 可视化组件
 *
 * 统一导出 CLI 可视化工具专用组件
 * 仅在 Tauri 桌面环境使用
 *
 * @example
 * ```tsx
 * import { CLIDiffViewer, CLIWorkspaceTree } from '@/components/features/cli-visualization';
 * import { isTauriEnvironment } from '@/lib/tauri';
 *
 * // 条件渲染
 * {isTauriEnvironment() && <CLIDiffViewer diff={diff} />}
 * ```
 */

// 组件
export { CLIDiffViewer } from './CLIDiffViewer';
export type { CLIDiffViewerProps } from './CLIDiffViewer';

export { CLIWorkspaceTree } from './CLIWorkspaceTree';
export type { CLIWorkspaceTreeProps, FileNode } from './CLIWorkspaceTree';

export { CLIFileIcon } from './CLIFileIcon';
export type { CLIFileIconProps } from './CLIFileIcon';

export { CLIFilePreview } from './CLIFilePreview';
export type { CLIFilePreviewProps } from './CLIFilePreview';

export { CLIContextMenu } from './CLIContextMenu';
export type { CLIContextMenuProps } from './CLIContextMenu';

// Hooks
export { useDiffParser } from './hooks/useDiffParser';
export type { ParsedDiff, DiffHunk, DiffLine, DiffLineType } from './hooks/useDiffParser';

export { useFilePreview } from './hooks/useFilePreview';
export type { UseFilePreviewReturn, FileType } from './hooks/useFilePreview';

export { useFileWatcher } from './hooks/useFileWatcher';
export type { UseFileWatcherReturn, UseFileWatcherOptions } from './hooks/useFileWatcher';
