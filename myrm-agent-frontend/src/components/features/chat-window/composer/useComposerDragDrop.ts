/**
 * [INPUT]
 * - @/hooks/ui/useDragDrop::useDragDrop (POS: 本地文件拖放)
 * - @/hooks/chat/usePriorChatComposerDrop::usePriorChatComposerDrop (POS: 把历史会话拖进输入区)
 * - @/hooks/message-input/useDesktopFolderDrop::useDesktopFolderDrop (POS: 桌面端把文件夹拖进输入区)
 *
 * [OUTPUT]
 * - useComposerDragDrop: 三类拖放来源合并后的事件处理器与拖放态。
 *
 * [POS]
 * 输入区接受三类拖放：本地文件、历史会话、桌面端文件夹。前两类挂在表单的拖放事件上，第三类来自 Tauri 的原生拖放事件，
 * 不经过表单；三者共用一个「正在拖放」覆盖层，所以在这里合并成一个出口。
 */
import { useMemo } from 'react';

import { usePriorChatComposerDrop } from '@/hooks/chat/usePriorChatComposerDrop';
import { useDesktopFolderDrop } from '@/hooks/message-input/useDesktopFolderDrop';
import { type DragHandlers, useDragDrop } from '@/hooks/ui/useDragDrop';

const ACCEPTED_DROP_TYPES = [
  'image/*',
  'video/*',
  'audio/*',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.ms-powerpoint',
  'text/csv',
  'text/plain',
  'text/markdown',
  'application/json',
];
const MAX_DROPPED_FILES = 20;

interface UseComposerDragDropOptions {
  disabled: boolean;
  onFilesSelected: (files: File[]) => void | Promise<void>;
}

export interface ComposerDragDrop {
  dragHandlers: DragHandlers;
  isDragging: boolean;
  /** The drag carries a prior chat, not files: the overlay says so. */
  isSessionDragging: boolean;
}

export function useComposerDragDrop({ disabled, onFilesSelected }: UseComposerDragDropOptions): ComposerDragDrop {
  const { isDragging: isFileDragging, dragHandlers: fileDragHandlers } = useDragDrop({
    onFilesSelected: (selectedFiles) => {
      void onFilesSelected(selectedFiles);
    },
    accept: ACCEPTED_DROP_TYPES,
    maxFiles: MAX_DROPPED_FILES,
    disabled,
  });
  const { isSessionDragging, dragHandlers: sessionDragHandlers } = usePriorChatComposerDrop({ disabled });
  const { isDraggingOver: isDesktopFolderDragging } = useDesktopFolderDrop({ disabled });

  const dragHandlers = useMemo<DragHandlers>(
    () => ({
      onDragEnter: (event) => {
        fileDragHandlers.onDragEnter(event);
        sessionDragHandlers.onDragEnter(event);
      },
      onDragOver: (event) => {
        fileDragHandlers.onDragOver(event);
        sessionDragHandlers.onDragOver(event);
      },
      onDragLeave: (event) => {
        fileDragHandlers.onDragLeave(event);
        sessionDragHandlers.onDragLeave(event);
      },
      onDrop: (event) => {
        fileDragHandlers.onDrop(event);
        sessionDragHandlers.onDrop(event);
      },
    }),
    [fileDragHandlers, sessionDragHandlers],
  );

  return {
    dragHandlers,
    isDragging: isFileDragging || isSessionDragging || isDesktopFolderDragging,
    isSessionDragging,
  };
}
