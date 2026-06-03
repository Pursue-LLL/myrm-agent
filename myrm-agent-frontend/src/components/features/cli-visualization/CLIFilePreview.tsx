/**
 * CLI 文件预览组件
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - file: 要预览的文件节点
 * - content: 文件内容
 * - fileType: 文件类型
 * - language: 代码语言
 * - onClose: 关闭回调
 * - onOpenInEditor: 在编辑器中打开回调
 *
 * [OUTPUT]
 * - CLIFilePreview: 文件预览组件
 *   - 代码文件：语法高亮
 *   - 图片文件：图片预览
 *   - 文本文件：纯文本显示
 *
 * [POS]
 * CLI 可视化工具的文件预览组件。支持代码高亮、图片预览、
 * 纯文本显示。仅在 Tauri 桌面环境使用。
 */

'use client';

import React, { memo, useCallback, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X,
  Copy,
  Check,
  ExternalLink,
  Folder,
  FileCode,
  FileText,
  Image as ImageIcon,
  AlertCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { FileNode } from './CLIWorkspaceTree';
import type { FileType } from './hooks/useFilePreview';
import { CLIFileIcon } from './CLIFileIcon';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

export interface CLIFilePreviewProps {
  /** 文件节点 */
  file: FileNode;
  /** 文件内容 */
  content: string | null;
  /** 文件类型 */
  fileType: FileType;
  /** 代码语言 */
  language: string | null;
  /** 加载中 */
  loading?: boolean;
  /** 错误信息 */
  error?: string | null;
  /** 关闭回调 */
  onClose: () => void;
  /** 在编辑器中打开 */
  onOpenInEditor?: (path: string) => void;
  /** 在 Finder 中显示 */
  onShowInFinder?: (path: string) => void;
  /** 类名 */
  className?: string;
}

/**
 * 代码预览（简单版，无 Shiki）
 */
const CodePreview: React.FC<{ content: string; language: string | null }> = memo(({ content, language: _language }) => {
  const lines = content.split('\n');

  return (
    <div className="font-mono text-xs overflow-auto">
      {lines.map((line, index) => (
        <div key={index} className="flex hover:bg-muted/30">
          <span className="w-12 text-right pr-4 py-0.5 text-muted-foreground select-none border-r border-border/50">
            {index + 1}
          </span>
          <code className="flex-1 px-4 py-0.5 whitespace-pre overflow-x-auto">{line || ' '}</code>
        </div>
      ))}
    </div>
  );
});
CodePreview.displayName = 'CodePreview';

/**
 * 图片预览
 */
const ImagePreview: React.FC<{ path: string }> = memo(({ path }) => {
  const [error, setError] = useState(false);

  // 在 Tauri 中，使用 asset: 协议加载本地文件
  const imageSrc = `asset://${path}`;

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <AlertCircle className="h-8 w-8 mb-2" />
        <span className="text-sm">Failed to load image</span>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center p-4">
      <img
        src={imageSrc}
        alt={path.split('/').pop()}
        className="max-w-full max-h-[400px] object-contain rounded"
        onError={() => setError(true)}
      />
    </div>
  );
});
ImagePreview.displayName = 'ImagePreview';

/**
 * 文本预览
 */
const TextPreview: React.FC<{ content: string }> = memo(({ content }) => (
  <pre className="p-4 font-mono text-xs whitespace-pre-wrap break-words">{content}</pre>
));
TextPreview.displayName = 'TextPreview';

/**
 * CLI 文件预览组件
 */
export const CLIFilePreview: React.FC<CLIFilePreviewProps> = memo(
  ({
    file,
    content,
    fileType,
    language,
    loading = false,
    error = null,
    onClose,
    onOpenInEditor,
    onShowInFinder,
    className,
  }) => {
    const [copied, setCopied] = useState(false);

    // 复制文件路径
    const handleCopyPath = useCallback(async () => {
      try {
        await writeToClipboard(file.path);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch {
        console.error('Failed to copy path');
      }
    }, [file.path]);

    // 在编辑器中打开
    const handleOpenInEditor = useCallback(async () => {
      if (onOpenInEditor) {
        onOpenInEditor(file.path);
      } else {
        // 默认使用 Tauri shell.open
        try {
          const { open } = await import('@tauri-apps/plugin-shell');
          await open(file.path);
        } catch (err) {
          console.error('Failed to open file:', err);
        }
      }
    }, [file.path, onOpenInEditor]);

    // 在 Finder 中显示
    const handleShowInFinder = useCallback(async () => {
      if (onShowInFinder) {
        onShowInFinder(file.path);
      } else {
        try {
          // 获取文件所在目录
          const dir = file.path.split('/').slice(0, -1).join('/');
          const { open } = await import('@tauri-apps/plugin-shell');
          await open(dir);
        } catch (err) {
          console.error('Failed to show in finder:', err);
        }
      }
    }, [file.path, onShowInFinder]);

    // 获取文件类型图标
    const getTypeIcon = () => {
      switch (fileType) {
        case 'code':
          return <FileCode className="h-4 w-4 text-blue-500" />;
        case 'image':
          return <ImageIcon className="h-4 w-4 text-purple-500" />;
        case 'text':
          return <FileText className="h-4 w-4 text-gray-500" />;
        default:
          return <CLIFileIcon filename={file.name} className="h-4 w-4" />;
      }
    };

    return (
      <AnimatePresence>
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          className={cn(
            'bg-background border border-border rounded-lg overflow-hidden shadow-xl',
            'flex flex-col max-h-[500px]',
            className,
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2 bg-muted/50 border-b border-border">
            <div className="flex items-center gap-2 min-w-0">
              {getTypeIcon()}
              <span className="text-sm font-medium truncate" title={file.path}>
                {file.name}
              </span>
              {language && (
                <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">{language}</span>
              )}
            </div>

            <div className="flex items-center gap-1">
              {/* 复制路径 */}
              <button
                onClick={handleCopyPath}
                className="p-1.5 rounded hover:bg-muted transition-colors"
                title="Copy path"
              >
                {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
              </button>
              {/* 在 Finder 中显示 */}
              <button
                onClick={handleShowInFinder}
                className="p-1.5 rounded hover:bg-muted transition-colors"
                title="Show in Finder"
              >
                <Folder className="h-4 w-4" />
              </button>
              {/* 在编辑器中打开 */}
              <button
                onClick={handleOpenInEditor}
                className="p-1.5 rounded hover:bg-muted transition-colors"
                title="Open in Editor"
              >
                <ExternalLink className="h-4 w-4" />
              </button>
              {/* 关闭 */}
              <button onClick={onClose} className="p-1.5 rounded hover:bg-muted transition-colors" title="Close">
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-auto">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin h-6 w-6 border-2 border-primary border-t-transparent rounded-full" />
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <AlertCircle className="h-8 w-8 mb-2 text-red-500" />
                <span className="text-sm">{error}</span>
              </div>
            ) : content === null ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <AlertCircle className="h-8 w-8 mb-2" />
                <span className="text-sm">No content available</span>
              </div>
            ) : fileType === 'image' ? (
              <ImagePreview path={content} />
            ) : fileType === 'code' ? (
              <CodePreview content={content} language={language} />
            ) : (
              <TextPreview content={content} />
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-2 bg-muted/30 border-t border-border text-xs text-muted-foreground truncate">
            {file.path}
          </div>
        </motion.div>
      </AnimatePresence>
    );
  },
);

CLIFilePreview.displayName = 'CLIFilePreview';

export default CLIFilePreview;
