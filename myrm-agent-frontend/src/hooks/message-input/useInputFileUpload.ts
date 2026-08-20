/**
 * [INPUT]
 * - @/services/file::uploadFiles (POS: 文件上传 API 客户端)
 * - @/store/useProviderStore::useProviderStore (POS: Provider 与模型能力状态)
 * - @/lib/utils/fileUtils::computeFileHash (POS: Browser file hashing utility)
 *
 * [OUTPUT]
 * - useInputFileUpload: 暴露粘贴/拖拽上传处理函数、乐观入队状态与延迟处理流水线。
 *
 * [POS]
 * 聊天输入文件上传 Hook。负责粘贴/拖拽文件上传、Office 剪贴板文本优先智能识别、SHA-256 去重和非阻塞延迟处理流水线。
 */

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { uploadFilesWithProgress } from '@/services/file';
import { toast } from '@/lib/utils/toast';
import { computeFileHash, isImageFile, isVideoFile, isAudioFile, getFileExtension } from '@/lib/utils/fileUtils';
import useProviderStore from '@/store/useProviderStore';
import { hasConfiguredVisionCapability, hasVisionFallbackForVideo } from '@/store/config/visionCapability';
import { showVisionNotConfiguredToast } from '@/store/config/visionConfigGap';
import { resetUploadController, getUploadSignal } from '@/services/uploadController';
import type { ActionMode, File as ChatFile } from '@/store/chat/types';

const MAX_FILE_BYTES = 50 * 1024 * 1024;
const MAX_VIDEO_BYTES = 100 * 1024 * 1024;
const MAX_AUDIO_BYTES = 25 * 1024 * 1024;
const RAG_DOC_THRESHOLD = 100 * 1024;
const RAG_DOC_EXTENSIONS = new Set(['pdf', 'docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt', 'ipynb']);

interface UseInputFileUploadParams {
  actionMode: ActionMode;
  files: ChatFile[];
  setFiles: React.Dispatch<React.SetStateAction<ChatFile[]>> | ((files: ChatFile[]) => void);
  setHideAttachList: (hide: boolean) => void;
}

export const useInputFileUpload = ({ actionMode, files, setFiles, setHideAttachList }: UseInputFileUploadParams) => {
  const tFiles = useTranslations('files');

  const updateFilesHelper = useCallback(
    (updater: (prev: ChatFile[]) => ChatFile[]) => {
      if (typeof setFiles === 'function') {
        setFiles(updater);
      }
    },
    [setFiles],
  );

  const uploadInputFiles = useCallback(
    async (inputFiles: globalThis.File[]) => {
      if (inputFiles.length === 0) {
        return;
      }

      // 1. 瞬时乐观插入：为每个输入文件分配临时 ID 与 Object URL，以 uploading 状态推入 UI
      const pendingItems = inputFiles.map((f) => {
        const tempId = `temp_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
        const ext = f.name.split('.').pop() || '';
        const isMedia = isImageFile(ext) || isVideoFile(ext);
        const previewUrl = isMedia ? URL.createObjectURL(f) : undefined;
        return {
          file: f,
          tempItem: {
            id: tempId,
            tempId,
            fileName: f.name,
            fileExtension: ext,
            fileType: 'uploaded' as const,
            status: 'uploading' as const,
            uploadPercent: 0,
            previewUrl,
          } satisfies ChatFile,
        };
      });

      const newOptimisticFiles = pendingItems.map((p) => p.tempItem);
      updateFilesHelper((prev) => [...prev, ...newOptimisticFiles]);
      setHideAttachList(false);

      // 2. 后台异步处理哈希与去重
      try {
        const existingHashes = new Set(files.map((f) => f.contentHash).filter(Boolean));
        const hashResults = await Promise.all(
          pendingItems.map(async ({ file, tempItem }) => ({
            file,
            tempItem,
            hash: await computeFileHash(file),
          })),
        );

        const dedupedItems: typeof hashResults = [];
        const duplicateTempIds = new Set<string>();

        for (const item of hashResults) {
          if (!existingHashes.has(item.hash)) {
            dedupedItems.push(item);
            existingHashes.add(item.hash);
          } else {
            duplicateTempIds.add(item.tempItem.tempId!);
          }
        }

        if (duplicateTempIds.size > 0) {
          // 移除重复项并释放对应 Object URL
          for (const item of hashResults) {
            if (duplicateTempIds.has(item.tempItem.tempId!) && item.tempItem.previewUrl) {
              URL.revokeObjectURL(item.tempItem.previewUrl);
            }
          }
          updateFilesHelper((prev) => prev.filter((f) => !f.tempId || !duplicateTempIds.has(f.tempId)));
          toast.info(tFiles('duplicateFiles'));
        }

        if (dedupedItems.length === 0) {
          return;
        }

        // 3. 后台发起上传请求
        resetUploadController();
        const filesToUpload = dedupedItems.map((d) => d.file);
        const uploadResults = await uploadFilesWithProgress(
          filesToUpload,
          (progress) => {
            updateFilesHelper((prev) =>
              prev.map((f) => {
                if (dedupedItems.some((d) => d.tempItem.tempId === f.tempId)) {
                  return { ...f, uploadPercent: progress.percent };
                }
                return f;
              }),
            );
          },
          getUploadSignal(),
        );

        if (uploadResults.uploaded_count === 0 || !uploadResults.files) {
          throw new Error('Upload returned empty file list');
        }

        // 4. 成功：将 uploading 乐观项就地升级为 ready 并赋值服务端元数据
        const uploadedMap = new Map<string, { fileId: string; fileUrl: string; hash: string }>();
        for (let i = 0; i < dedupedItems.length; i++) {
          const rawFile = uploadResults.files[i];
          if (rawFile) {
            uploadedMap.set(dedupedItems[i].tempItem.tempId!, {
              fileId: rawFile.fileId,
              fileUrl: rawFile.fileUrl,
              hash: dedupedItems[i].hash,
            });
          }
        }

        updateFilesHelper((prev) =>
          prev.map((f) => {
            if (f.tempId && uploadedMap.has(f.tempId)) {
              const res = uploadedMap.get(f.tempId)!;
              if (f.previewUrl) {
                URL.revokeObjectURL(f.previewUrl);
              }
              return {
                id: res.fileId,
                fileName: f.fileName,
                fileExtension: f.fileExtension,
                fileUrl: res.fileUrl,
                fileType: 'uploaded' as const,
                contentHash: res.hash,
                status: 'ready' as const,
                uploadPercent: 100,
              };
            }
            return f;
          }),
        );

        toast.success(tFiles('uploadSuccess'), {
          description: tFiles('uploadedCount', { count: uploadResults.uploaded_count }),
        });

        for (const { file } of dedupedItems) {
          const ext = getFileExtension(file.name);
          if (RAG_DOC_EXTENSIONS.has(ext) && file.size > RAG_DOC_THRESHOLD) {
            const sizeMB = `${(file.size / 1024 / 1024).toFixed(1)}MB`;
            toast.info(tFiles('largeDocIndexing'), {
              description: tFiles('largeDocIndexingDesc', { name: file.name, size: sizeMB }),
            });
          }
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        // 标记为 error 状态
        updateFilesHelper((prev) =>
          prev.map((f) => {
            if (pendingItems.some((p) => p.tempItem.tempId === f.tempId)) {
              return { ...f, status: 'error' as const };
            }
            return f;
          }),
        );
        toast.error(tFiles('uploadError'));
      }
    },
    [files, updateFilesHelper, setHideAttachList, tFiles],
  );

  const handleDroppedFiles = useCallback(
    async (droppedFiles: globalThis.File[]) => {
      if (actionMode === 'fast') {
        return;
      }

      const oversized = droppedFiles.find((f) => {
        const ext = getFileExtension(f.name);
        if (isVideoFile(ext)) {
          return f.size > MAX_VIDEO_BYTES;
        }
        if (isAudioFile(ext)) {
          return f.size > MAX_AUDIO_BYTES;
        }
        return f.size > MAX_FILE_BYTES;
      });
      if (oversized) {
        const sizeMB = `${(oversized.size / 1024 / 1024).toFixed(1)}MB`;
        const ext = getFileExtension(oversized.name);
        if (isVideoFile(ext)) {
          toast.error(tFiles('videoTooLarge'), { description: tFiles('videoTooLargeDesc', { size: sizeMB }) });
        } else if (isAudioFile(ext)) {
          toast.error(tFiles('audioTooLarge'), { description: tFiles('audioTooLargeDesc', { size: sizeMB }) });
        } else {
          toast.error(tFiles('fileTooLarge'), {
            description: tFiles('fileTooLargeDesc', { name: oversized.name, size: sizeMB }),
          });
        }
        return;
      }

      const hasImages = droppedFiles.some((f) => isImageFile(getFileExtension(f.name)));
      const hasVideos = droppedFiles.some((f) => isVideoFile(getFileExtension(f.name)));
      if (hasImages || hasVideos) {
        const { defaultModelConfig, getModelInfo } = useProviderStore.getState();
        const selection = defaultModelConfig?.baseModel?.primary;
        if (selection) {
          const modelInfo = getModelInfo(selection.providerId, selection.model);
          const hasVision =
            modelInfo?.supports_vision || hasConfiguredVisionCapability(defaultModelConfig, getModelInfo);
          const hasVideoFallback = hasVisionFallbackForVideo(defaultModelConfig, getModelInfo);
          if (hasImages && !hasVision) {
            showVisionNotConfiguredToast('image');
          }
          if (hasVideos && !modelInfo?.supports_video_input && !hasVideoFallback) {
            showVisionNotConfiguredToast('video');
          }
        }
      }

      await uploadInputFiles(droppedFiles);
    },
    [actionMode, uploadInputFiles, tFiles],
  );

  const handlePaste = useCallback(
    async (e: React.ClipboardEvent) => {
      if (actionMode === 'fast') {
        return;
      }

      const dt = e.clipboardData;
      if (!dt?.items) {
        return;
      }

      const imageFiles: globalThis.File[] = [];
      const otherFiles: globalThis.File[] = [];
      for (let i = 0; i < dt.items.length; i++) {
        const item = dt.items[i];
        if (item.kind !== 'file') {
          continue;
        }
        const file = item.getAsFile();
        if (!file) {
          continue;
        }
        if (file.type.startsWith('image/')) {
          imageFiles.push(file);
        } else {
          otherFiles.push(file);
        }
      }

      const allFiles = [...otherFiles, ...imageFiles];
      if (allFiles.length === 0) {
        return;
      }

      if (otherFiles.length === 0 && imageFiles.length > 0) {
        const plain = dt.getData('text/plain').trim();
        const hasHtml = dt.getData('text/html').trim().length > 0;
        const looksLikeImagePath =
          plain.length > 0 && !plain.includes('\n') && /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(plain);
        if ((plain.length > 0 || hasHtml) && !looksLikeImagePath) {
          return;
        }
      }

      e.preventDefault();
      await handleDroppedFiles(allFiles);
    },
    [actionMode, handleDroppedFiles],
  );

  return {
    isUploadingPaste: false,
    handlePaste,
    handleDroppedFiles,
    uploadInputFiles,
  };
};
