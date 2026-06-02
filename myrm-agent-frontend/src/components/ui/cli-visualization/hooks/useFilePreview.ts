/**
 * 文件预览 Hook
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - file: 要预览的文件节点
 * - @tauri-apps/plugin-fs: 文件读取
 *
 * [OUTPUT]
 * - useFilePreview: 文件预览 Hook
 *   - previewFile: 当前预览的文件
 *   - isOpen: 预览是否打开
 *   - content: 文件内容
 *   - loading: 加载状态
 *   - error: 错误信息
 *   - open/close: 打开/关闭预览
 *
 * [POS]
 * CLI 可视化工具的文件预览 Hook。通过 Tauri API 读取
 * 文件内容，支持文本、代码、图片等类型。
 */

import { useState, useCallback } from 'react';
import { isTauriEnvironment } from '@/lib/tauri';
import type { FileNode } from '../CLIWorkspaceTree';

/** 文件类型 */
export type FileType = 'code' | 'text' | 'image' | 'binary' | 'unknown';

/** 预览状态 */
export interface FilePreviewState {
  file: FileNode | null;
  content: string | null;
  fileType: FileType;
  language: string | null;
}

export interface UseFilePreviewReturn {
  /** 预览状态 */
  previewFile: FileNode | null;
  isOpen: boolean;
  content: string | null;
  fileType: FileType;
  language: string | null;
  loading: boolean;
  error: string | null;

  /** 操作 */
  openPreview: (file: FileNode) => Promise<void>;
  closePreview: () => void;
}

/** 代码文件扩展名 → 语言映射 */
const CODE_EXTENSIONS: Record<string, string> = {
  ts: 'typescript',
  tsx: 'tsx',
  js: 'javascript',
  jsx: 'jsx',
  py: 'python',
  rb: 'ruby',
  go: 'go',
  rs: 'rust',
  java: 'java',
  c: 'c',
  cpp: 'cpp',
  h: 'c',
  hpp: 'cpp',
  cs: 'csharp',
  php: 'php',
  swift: 'swift',
  kt: 'kotlin',
  scala: 'scala',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  xml: 'xml',
  html: 'html',
  css: 'css',
  scss: 'scss',
  less: 'less',
  md: 'markdown',
  sql: 'sql',
  sh: 'bash',
  bash: 'bash',
  zsh: 'bash',
  toml: 'toml',
  ini: 'ini',
  conf: 'ini',
};

/** 图片扩展名 */
const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'ico', 'bmp'];

/** 文本扩展名 */
const TEXT_EXTENSIONS = ['txt', 'log', 'env', 'gitignore', 'dockerignore'];

/**
 * 获取文件类型
 */
function getFileType(filename: string): { type: FileType; language: string | null } {
  const ext = filename.split('.').pop()?.toLowerCase() || '';

  if (CODE_EXTENSIONS[ext]) {
    return { type: 'code', language: CODE_EXTENSIONS[ext] };
  }
  if (IMAGE_EXTENSIONS.includes(ext)) {
    return { type: 'image', language: null };
  }
  if (TEXT_EXTENSIONS.includes(ext)) {
    return { type: 'text', language: null };
  }

  return { type: 'unknown', language: null };
}

/**
 * 文件预览 Hook
 */
export function useFilePreview(): UseFilePreviewReturn {
  const [state, setState] = useState<FilePreviewState>({
    file: null,
    content: null,
    fileType: 'unknown',
    language: null,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * 打开文件预览
   */
  const openPreview = useCallback(async (file: FileNode) => {
    if (file.type === 'directory') {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const { type, language } = getFileType(file.name);

      // 图片文件不需要读取内容，直接显示路径
      if (type === 'image') {
        setState({
          file,
          content: file.path, // 图片路径
          fileType: type,
          language: null,
        });
        setLoading(false);
        return;
      }

      // 非 Tauri 环境无法读取文件
      if (!isTauriEnvironment()) {
        setState({
          file,
          content: null,
          fileType: type,
          language,
        });
        setError('File preview requires Tauri environment');
        setLoading(false);
        return;
      }

      // 读取文件内容
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const fs = (await import('@tauri-apps/plugin-fs')) as any;
      const { readTextFile } = fs;

      if (!readTextFile) {
        throw new Error('Tauri FS plugin not available');
      }

      const content = await readTextFile(file.path);

      setState({
        file,
        content,
        fileType: type,
        language,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to read file');
      setState({
        file,
        content: null,
        fileType: 'unknown',
        language: null,
      });
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * 关闭预览
   */
  const closePreview = useCallback(() => {
    setState({
      file: null,
      content: null,
      fileType: 'unknown',
      language: null,
    });
    setError(null);
  }, []);

  return {
    previewFile: state.file,
    isOpen: state.file !== null,
    content: state.content,
    fileType: state.fileType,
    language: state.language,
    loading,
    error,
    openPreview,
    closePreview,
  };
}

export default useFilePreview;
