import { useCallback, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useTranslations } from 'next-intl';

export interface UseDragDropOptions {
  onFilesSelected: (files: File[]) => void;
  accept?: string[];
  maxFiles?: number;
  disabled?: boolean;
}

export interface DragHandlers {
  onDragEnter: (e: React.DragEvent) => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
}

export interface UseDragDropReturn {
  isDragging: boolean;
  dragHandlers: DragHandlers;
}

export function useDragDrop(options: UseDragDropOptions): UseDragDropReturn {
  const { onFilesSelected, accept, maxFiles = 10, disabled = false } = options;

  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);
  const t = useTranslations('files');

  const isFileTypeAccepted = useCallback(
    (file: File): boolean => {
      if (!accept || accept.length === 0) return true;

      return accept.some((pattern) => {
        if (pattern.endsWith('/*')) {
          const category = pattern.slice(0, -2);
          return file.type.startsWith(category + '/');
        }
        return file.type === pattern;
      });
    },
    [accept],
  );

  const handleDragEnter = useCallback(
    (e: React.DragEvent) => {
      if (disabled) return;

      e.preventDefault();
      e.stopPropagation();

      // P2: 只在拖拽文件时显示overlay（非文本/链接）
      if (!e.dataTransfer.types.includes('Files')) {
        return;
      }

      // P0: 使用计数器防止嵌套元素触发dragleave导致闪烁
      dragCounter.current++;
      if (!isDragging) {
        setIsDragging(true);
      }
    },
    [disabled, isDragging],
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      if (disabled) return;

      e.preventDefault();
      e.stopPropagation();

      // P2: 只在拖拽文件时响应
      if (!e.dataTransfer.types.includes('Files')) {
        return;
      }

      // 设置dropEffect为copy（显示拖拽光标）
      e.dataTransfer.dropEffect = 'copy';
    },
    [disabled],
  );

  const handleDragLeave = useCallback(
    (e: React.DragEvent) => {
      if (disabled) return;

      e.preventDefault();
      e.stopPropagation();

      // P0: 使用计数器防止嵌套元素触发dragleave导致闪烁
      dragCounter.current--;

      // P1: 边界检测 - 拖拽到窗口边界外时强制重置
      const { clientX, clientY } = e;
      if (clientX <= 0 || clientY <= 0 || clientX >= window.innerWidth || clientY >= window.innerHeight) {
        dragCounter.current = 0;
      }

      if (dragCounter.current === 0) {
        setIsDragging(false);
      }
    },
    [disabled],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      if (disabled) return;

      e.preventDefault();
      e.stopPropagation();

      // 重置拖拽状态
      dragCounter.current = 0;
      setIsDragging(false);

      const items = e.dataTransfer.items;
      if (!items) return;

      const fileArray: File[] = [];

      // 提取文件
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.kind === 'file') {
          const file = item.getAsFile();
          if (file) {
            fileArray.push(file);
          }
        }
      }

      if (fileArray.length === 0) {
        return;
      }

      // 文件数量限制
      if (fileArray.length > maxFiles) {
        toast.error(t('tooManyFiles', { max: maxFiles }));
        return;
      }

      // 文件类型验证
      const invalidFiles = fileArray.filter((file) => !isFileTypeAccepted(file));
      if (invalidFiles.length > 0) {
        const invalidTypes = invalidFiles.map((f) => f.type || 'unknown').join(', ');
        toast.error(t('invalidFileType', { types: invalidTypes }));
        return;
      }

      // 调用回调
      onFilesSelected(fileArray);
    },
    [disabled, maxFiles, isFileTypeAccepted, onFilesSelected, t],
  );

  const dragHandlers: DragHandlers = {
    onDragEnter: handleDragEnter,
    onDragOver: handleDragOver,
    onDragLeave: handleDragLeave,
    onDrop: handleDrop,
  };

  return {
    isDragging,
    dragHandlers,
  };
}
