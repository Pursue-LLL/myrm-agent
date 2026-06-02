/**
 * 文件监视 Hook
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - workspacePath: 工作区路径
 * - enabled: 是否启用监视
 *
 * [OUTPUT]
 * - useFileWatcher: 文件监视 Hook
 *   - files: 文件列表
 *   - loading: 是否加载中
 *   - error: 错误信息
 *   - refresh: 手动刷新
 *
 * [POS]
 * CLI 可视化工具的文件监视 Hook。通过 Tauri API 监视
 * 工作区文件变化，自动更新文件列表。仅在 Tauri 环境工作。
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { isTauriEnvironment } from '@/lib/tauri';
import type { FileNode } from '../CLIWorkspaceTree';

export interface UseFileWatcherOptions {
  /** 是否启用监视 */
  enabled?: boolean;
  /** 初始加载 */
  loadOnMount?: boolean;
  /** 忽略的文件模式 */
  ignorePatterns?: string[];
}

export interface UseFileWatcherReturn {
  /** 文件列表 */
  files: FileNode[];
  /** 是否加载中 */
  loading: boolean;
  /** 错误信息 */
  error: string | null;
  /** 手动刷新 */
  refresh: () => Promise<void>;
}

/**
 * 默认忽略模式
 */
const DEFAULT_IGNORE_PATTERNS = [
  'node_modules',
  '.git',
  '.next',
  '__pycache__',
  '.venv',
  'dist',
  'build',
  '.cache',
  '.DS_Store',
];

/**
 * 文件监视 Hook
 *
 * @param workspacePath - 工作区路径（为空时不执行）
 * @param options - 配置选项
 */
export function useFileWatcher(
  workspacePath?: string | null,
  options: UseFileWatcherOptions = {},
): UseFileWatcherReturn {
  const { enabled = true, loadOnMount = true, ignorePatterns = DEFAULT_IGNORE_PATTERNS } = options;

  const [files, setFiles] = useState<FileNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  /**
   * 读取目录内容
   */
  const readDirectory = useCallback(
    async (path: string): Promise<FileNode[]> => {
      if (!isTauriEnvironment()) {
        return [];
      }

      try {
        // 动态导入 Tauri API（类型安全处理）
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const fs = (await import('@tauri-apps/plugin-fs')) as any;
        const { readDir, stat } = fs;

        if (!readDir || !stat) {
          throw new Error('Tauri FS plugin not available');
        }

        const entries = await readDir(path);
        const nodes: FileNode[] = [];

        for (const entry of entries) {
          // 检查是否应该忽略
          const shouldIgnore = ignorePatterns.some((pattern) => entry.name.includes(pattern) || entry.name === pattern);
          if (shouldIgnore) continue;

          const fullPath = `${path}/${entry.name}`;

          try {
            const info = await stat(fullPath);
            const isDirectory = info.isDirectory;

            const node: FileNode = {
              name: entry.name,
              path: fullPath,
              type: isDirectory ? 'directory' : 'file',
              size: isDirectory ? undefined : info.size,
            };

            // 递归读取子目录（限制深度为 3）
            if (isDirectory && workspacePath) {
              const depth = fullPath.split('/').length - workspacePath.split('/').length;
              if (depth < 3) {
                node.children = await readDirectory(fullPath);
              }
            }

            nodes.push(node);
          } catch {
            // 忽略无法访问的文件
            continue;
          }
        }

        // 排序：目录在前，文件在后，按名称排序
        return nodes.sort((a, b) => {
          if (a.type !== b.type) {
            return a.type === 'directory' ? -1 : 1;
          }
          return a.name.localeCompare(b.name);
        });
      } catch (err) {
        console.error('Failed to read directory:', err);
        throw err;
      }
    },
    [workspacePath, ignorePatterns],
  );

  /**
   * 刷新文件列表
   */
  const refresh = useCallback(async () => {
    if (!workspacePath || !enabled || !isTauriEnvironment()) {
      return;
    }

    // 取消之前的请求
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setLoading(true);
    setError(null);

    try {
      const result = await readDirectory(workspacePath);
      setFiles(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to read workspace');
    } finally {
      setLoading(false);
    }
  }, [workspacePath, enabled, readDirectory]);

  // 初始加载
  useEffect(() => {
    if (loadOnMount && enabled && workspacePath) {
      refresh();
    }

    return () => {
      abortControllerRef.current?.abort();
    };
  }, [loadOnMount, enabled, workspacePath, refresh]);

  return {
    files,
    loading,
    error,
    refresh,
  };
}

export default useFileWatcher;
