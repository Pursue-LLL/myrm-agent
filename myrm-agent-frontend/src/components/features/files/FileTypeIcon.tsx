/**
 * 文件类型图标组件
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - filename: 文件名
 * - isDirectory: 是否为目录
 * - isExpanded: 目录是否展开
 *
 * [OUTPUT]
 * - FileTypeIcon: 根据文件类型显示对应图标
 *
 * [POS]
 * 文件展示层的共享图标组件。根据扩展名返回对应图标与配色，
 * 供文件树、文件预览与 diff 视图复用。
 */

import React, { memo } from 'react';
import {
  File,
  FileCode,
  FileJson,
  FileText,
  Folder,
  FolderOpen,
  Image,
  FileType,
  FileArchive,
  FileVideo,
  FileAudio,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export interface FileTypeIconProps {
  filename: string;
  isDirectory?: boolean;
  isExpanded?: boolean;
  className?: string;
}

/** 文件扩展名到图标的映射 */
const extensionIconMap: Record<string, React.FC<{ className?: string }>> = {
  // 代码文件
  ts: FileCode,
  tsx: FileCode,
  js: FileCode,
  jsx: FileCode,
  py: FileCode,
  rb: FileCode,
  go: FileCode,
  rs: FileCode,
  java: FileCode,
  c: FileCode,
  cpp: FileCode,
  h: FileCode,
  hpp: FileCode,
  cs: FileCode,
  php: FileCode,
  swift: FileCode,
  kt: FileCode,
  scala: FileCode,

  // JSON/配置
  json: FileJson,
  yaml: FileJson,
  yml: FileJson,
  toml: FileJson,
  xml: FileJson,

  // 文档
  md: FileText,
  markdown: FileText,
  txt: FileText,
  rst: FileText,
  doc: FileText,
  docx: FileText,
  pdf: FileText,

  // 样式
  css: FileType,
  scss: FileType,
  sass: FileType,
  less: FileType,

  // 图片
  png: Image,
  jpg: Image,
  jpeg: Image,
  gif: Image,
  webp: Image,
  svg: Image,
  ico: Image,
  bmp: Image,

  // 压缩文件
  zip: FileArchive,
  tar: FileArchive,
  gz: FileArchive,
  rar: FileArchive,
  '7z': FileArchive,

  // 视频
  mp4: FileVideo,
  webm: FileVideo,
  avi: FileVideo,
  mov: FileVideo,
  mkv: FileVideo,

  // 音频
  mp3: FileAudio,
  wav: FileAudio,
  ogg: FileAudio,
  flac: FileAudio,
};

/** 获取文件扩展名 */
function getExtension(filename: string): string {
  const parts = filename.split('.');
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : '';
}

export const FileTypeIcon: React.FC<FileTypeIconProps> = memo(
  ({ filename, isDirectory = false, isExpanded = false, className }) => {
    const iconClass = cn('h-4 w-4 flex-shrink-0', className);

    if (isDirectory) {
      return isExpanded ? (
        <FolderOpen className={cn(iconClass, 'text-amber-500')} />
      ) : (
        <Folder className={cn(iconClass, 'text-amber-500')} />
      );
    }

    const ext = getExtension(filename);
    const IconComponent = extensionIconMap[ext] || File;

    const colorClass = ext.match(/^(ts|tsx)$/)
      ? 'text-blue-500'
      : ext.match(/^(js|jsx)$/)
        ? 'text-yellow-500'
        : ext.match(/^(py)$/)
          ? 'text-green-500'
          : ext.match(/^(rs)$/)
            ? 'text-orange-500'
            : ext.match(/^(go)$/)
              ? 'text-cyan-500'
              : 'text-muted-foreground';

    return <IconComponent className={cn(iconClass, colorClass)} />;
  },
);

FileTypeIcon.displayName = 'FileTypeIcon';

export default FileTypeIcon;
