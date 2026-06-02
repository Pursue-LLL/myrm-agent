/**
 * [INPUT]
 * - @/services/file::uploadFiles (POS: 文件上传 API 客户端)
 * - @/store/useProviderStore::useProviderStore (POS: Provider 与模型能力状态)
 * - @/lib/utils/fileUtils::computeFileHash (POS: Browser file hashing utility)
 *
 * [OUTPUT]
 * - useInputFileUpload: exposes paste/drop upload handlers and upload state.
 *
 * [POS]
 * 聊天输入文件上传 Hook。负责粘贴图片、拖拽文件、SHA-256 去重和上传后附件状态转换。
 */

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { uploadFiles } from '@/services/file';
import { toast } from '@/lib/utils/toast';
import { computeFileHash } from '@/lib/utils/fileUtils';
import useProviderStore from '@/store/useProviderStore';
import { resetUploadController, getUploadSignal } from '@/services/uploadController';
import type { ActionMode, File as ChatFile } from '@/store/chat/types';

interface UseInputFileUploadParams {
  actionMode: ActionMode;
  files: ChatFile[];
  setFiles: (files: ChatFile[]) => void;
  setHideAttachList: (hide: boolean) => void;
}

export const useInputFileUpload = ({ actionMode, files, setFiles, setHideAttachList }: UseInputFileUploadParams) => {
  const tFiles = useTranslations('files');
  const [isUploadingPaste, setIsUploadingPaste] = useState(false);

  const uploadInputFiles = useCallback(
    async (inputFiles: globalThis.File[]) => {
      if (inputFiles.length === 0) return;

      const existingHashes = new Set(files.map((f) => f.contentHash).filter(Boolean));
      const hashResults = await Promise.all(
        inputFiles.map(async (file) => ({ file, hash: await computeFileHash(file) })),
      );
      const dedupedFiles: globalThis.File[] = [];
      const hashMap = new Map<string, string>();
      for (const { file, hash } of hashResults) {
        if (!existingHashes.has(hash)) {
          dedupedFiles.push(file);
          hashMap.set(file.name, hash);
          existingHashes.add(hash);
        }
      }

      if (dedupedFiles.length === 0) {
        toast.info(tFiles('duplicateFiles'));
        return;
      }

      resetUploadController();
      const uploadResults = await uploadFiles(dedupedFiles, getUploadSignal());
      if (uploadResults.uploaded_count === 0 || !uploadResults.files) return;

      const newFiles = uploadResults.files.map((file) => ({
        fileName: file.fileName,
        fileExtension: file.fileName.split('.').pop() || '',
        fileUrl: file.fileUrl,
        fileType: 'uploaded' as const,
        contentHash: hashMap.get(file.fileName),
      }));
      setFiles([...files, ...newFiles]);
      setHideAttachList(false);
      toast.success(tFiles('uploadSuccess'), {
        description: tFiles('uploadedCount', { count: uploadResults.uploaded_count }),
      });
    },
    [files, setFiles, setHideAttachList, tFiles],
  );

  const canAcceptPastedImages = useCallback(() => {
    const { defaultModelConfig, getModelInfo } = useProviderStore.getState();
    const selection = defaultModelConfig?.baseModel?.primary;
    if (!selection) return true;

    const modelInfo = getModelInfo(selection.providerId, selection.model);
    const fallbackSelection = defaultModelConfig?.visionFallbackModel;
    const fallbackModelInfo = fallbackSelection
      ? getModelInfo(fallbackSelection.providerId, fallbackSelection.model)
      : null;
    return Boolean(modelInfo?.supports_vision || fallbackModelInfo?.supports_vision);
  }, []);

  const handlePaste = useCallback(
    async (e: React.ClipboardEvent) => {
      if (actionMode === 'fast') return;

      const items = e.clipboardData?.items;
      if (!items) return;

      const imageItems: DataTransferItem[] = [];
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.indexOf('image') !== -1) {
          imageItems.push(items[i]);
        }
      }
      if (imageItems.length === 0) return;

      if (!canAcceptPastedImages()) {
        toast.warning(tFiles('modelNotSupportVision'));
        return;
      }

      e.preventDefault();
      setIsUploadingPaste(true);
      try {
        const imageFiles: globalThis.File[] = [];
        for (const item of imageItems) {
          const file = item.getAsFile();
          if (file) {
            imageFiles.push(file);
          }
        }
        await uploadInputFiles(imageFiles);
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        toast.error(tFiles('uploadError'));
      } finally {
        setIsUploadingPaste(false);
      }
    },
    [actionMode, canAcceptPastedImages, uploadInputFiles, tFiles],
  );

  const handleDroppedFiles = useCallback(
    async (droppedFiles: globalThis.File[]) => {
      if (actionMode === 'fast') return;
      setIsUploadingPaste(true);
      try {
        await uploadInputFiles(droppedFiles);
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        toast.error(tFiles('uploadError'));
      } finally {
        setIsUploadingPaste(false);
      }
    },
    [actionMode, uploadInputFiles, tFiles],
  );

  return {
    isUploadingPaste,
    handlePaste,
    handleDroppedFiles,
  };
};
