import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import type { KanbanTask } from '@/services/kanban';
import { updateTask } from '@/services/kanban';
import { getApiUrl } from '@/lib/api';

interface UseKanbanTaskDrawerAttachmentsParams {
  task: KanbanTask | null;
  open: boolean;
  onRefresh: () => void;
  t: (key: string) => string;
}

export function useKanbanTaskDrawerAttachments({
  task,
  open,
  onRefresh,
  t,
}: UseKanbanTaskDrawerAttachmentsParams) {
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const handleAttachUpload = useCallback(
    async (files: File[]) => {
      if (!task || files.length === 0) return;
      const existingCount = task.attachment_ids?.length ?? 0;
      const remaining = 10 - existingCount;
      if (remaining <= 0) {
        toast.warning(t('attachmentLimitExceeded'));
        return;
      }
      const toUpload = files.slice(0, remaining);
      if (toUpload.length < files.length) {
        toast.warning(t('attachmentLimitExceeded'));
      }
      setUploadingAttachment(true);
      try {
        const results = await Promise.allSettled(
          toUpload.map(async (file) => {
            const formData = new FormData();
            formData.append('file', file);
            const resp = await fetch(getApiUrl('/files/upload'), { method: 'POST', body: formData });
            if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
            const data = await resp.json();
            return data.file_id as string;
          }),
        );
        const newIds = results
          .filter((r): r is PromiseFulfilledResult<string> => r.status === 'fulfilled')
          .map((r) => r.value);
        const failedCount = results.filter((r) => r.status === 'rejected').length;
        if (failedCount > 0) {
          toast.error(t('attachmentUploadError'));
        }
        if (newIds.length > 0) {
          const existingIds = task.attachment_ids ?? [];
          await updateTask(task.task_id, { attachment_ids: [...existingIds, ...newIds] });
          onRefresh();
          toast.success(t('attachmentAdded'));
        }
      } catch {
        toast.error(t('attachmentUploadError'));
      }
      setUploadingAttachment(false);
    },
    [task, onRefresh, t],
  );

  const handleRemoveAttachment = useCallback(
    async (fileId: string) => {
      if (!task) return;
      const updated = (task.attachment_ids ?? []).filter((id) => id !== fileId);
      try {
        await updateTask(task.task_id, { attachment_ids: updated });
        onRefresh();
        toast.success(t('attachmentRemoved'));
      } catch {
        toast.error(t('attachmentRemoveError'));
      }
    },
    [task, onRefresh, t],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const files = Array.from(e.dataTransfer.files);
      handleAttachUpload(files);
    },
    [handleAttachUpload],
  );

  const handlePaste = useCallback(
    (e: ClipboardEvent) => {
      const items = Array.from(e.clipboardData?.items ?? []);
      const files = items
        .filter((item) => item.kind === 'file')
        .map((item) => item.getAsFile())
        .filter((f): f is File => f !== null);
      if (files.length > 0) {
        e.preventDefault();
        handleAttachUpload(files);
      }
    },
    [handleAttachUpload],
  );

  useEffect(() => {
    if (!open) return;
    document.addEventListener('paste', handlePaste);
    return () => document.removeEventListener('paste', handlePaste);
  }, [open, handlePaste]);

  return {
    uploadingAttachment,
    dragOver,
    setDragOver,
    handleAttachUpload,
    handleRemoveAttachment,
    handleDrop,
  };
}
