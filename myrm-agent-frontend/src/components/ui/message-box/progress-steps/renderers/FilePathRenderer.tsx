import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { File } from 'lucide-react';
import type { FilePathItem } from '../utils';

interface FilePathRendererProps {
  items: FilePathItem[];
  messageId: string;
  stepIndex: number;
}

/**
 * 截断文件路径，保留文件名和部分路径
 * 如果路径太长，从前面截断（添加 ...）
 * @param path 完整路径
 * @param maxLength 最大显示长度
 */
const truncatePath = (path: string, maxLength: number = 50): string => {
  if (path.length <= maxLength) {
    return path;
  }
  // 从前面截断，保留后面的内容（文件名）
  return '...' + path.slice(-(maxLength - 3));
};

/**
 * 文件路径渲染器
 * 用于展示 file_editor view 命令读取的文件列表
 * 超长路径会从前面截断，确保文件名完整显示
 */
const FilePathRenderer: React.FC<FilePathRendererProps> = ({ items, messageId, stepIndex }) => {
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item, index) => (
        <div
          key={`${messageId}-step-${stepIndex}-file-${index}`}
          className={cn(
            'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md',
            'bg-muted/50 border border-border/50',
            'text-xs font-mono text-muted-foreground',
            'transition-colors duration-200 hover:bg-muted hover:border-border',
          )}
          title={item.file_path}
        >
          <File className="w-3 h-3 flex-shrink-0" />
          <span>{truncatePath(item.file_path)}</span>
        </div>
      ))}
    </div>
  );
};

export default FilePathRenderer;
