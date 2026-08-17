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
 * 聊天输入文件上传 Hook。负责粘贴/拖拽文件上传、Office 剪贴板文本优先智能识别、SHA-256 去重和上传后附件状态转换。
 */

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { uploadFiles } from '@/services/file';
import { toast } from '@/lib/utils/toast';
import { computeFileHash, isImageFile, isVideoFile, isAudioFile, getFileExtension } from '@/lib/utils/fileUtils';
import useProviderStore from '@/store/useProviderStore';
import {
  hasConfiguredVisionCapability,
  hasVisionFallbackForVideo,
} from '@/store/config/visionCapability';
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
  setFiles: (files: ChatFile[]) => void;
  setHideAttachList: (hide: boolean) => void;
}

export const useInputFileUpload = ({ actionMode, files, setFiles, setHideAttachList }: UseInputFileUploadParams) => {
  const tFiles = useTranslations('files');
  const [isUploadingPaste, setIsUploadingPaste] = useState(false);

  const uploadInputFiles = useCallback(
    async (inputFiles: globalThis.File[]) => {
      if (inputFiles.length === 0) {return;}

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
      if (uploadResults.uploaded_count === 0 || !uploadResults.files) {return;}

      const newFiles = uploadResults.files.map((file) => ({
        id: file.fileId,
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

      for (const f of dedupedFiles) {
        const ext = getFileExtension(f.name);
        if (RAG_DOC_EXTENSIONS.has(ext) && f.size > RAG_DOC_THRESHOLD) {
          const sizeMB = `${(f.size / 1024 / 1024).toFixed(1)}MB`;
          toast.info(tFiles('largeDocIndexing'), {
            description: tFiles('largeDocIndexingDesc', { name: f.name, size: sizeMB }),
          });
        }
      }
    },
    [files, setFiles, setHideAttachList, tFiles],
  );

  const handleDroppedFiles = useCallback(
    async (droppedFiles: globalThis.File[]) => {
      if (actionMode === 'fast') {return;}

      const oversized = droppedFiles.find((f) => {
        const ext = getFileExtension(f.name);
        if (isVideoFile(ext)) {return f.size > MAX_VIDEO_BYTES;}
        if (isAudioFile(ext)) {return f.size > MAX_AUDIO_BYTES;}
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
          toast.error(tFiles('fileTooLarge'), { description: tFiles('fileTooLargeDesc', { name: oversized.name, size: sizeMB }) });
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
          const hasVision = modelInfo?.supports_vision || hasConfiguredVisionCapability(defaultModelConfig, getModelInfo);
          const hasVideoFallback = hasVisionFallbackForVideo(defaultModelConfig, getModelInfo);
          if (hasImages && !hasVision) {
            showVisionNotConfiguredToast('image');
          }
          if (hasVideos && !modelInfo?.supports_video_input && !hasVideoFallback) {
            showVisionNotConfiguredToast('video');
          }
        }
      }

      setIsUploadingPaste(true);
      try {
        await uploadInputFiles(droppedFiles);
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {return;}
        toast.error(tFiles('uploadError'));
      } finally {
        setIsUploadingPaste(false);
      }
    },
    [actionMode, uploadInputFiles, tFiles],
  );

  const handlePaste = useCallback(
    async (e: React.ClipboardEvent) => {
      if (actionMode === 'fast') {return;}

      const dt = e.clipboardData;
      if (!dt?.items) {return;}

      const imageFiles: globalThis.File[] = [];
      const otherFiles: globalThis.File[] = [];
      for (let i = 0; i < dt.items.length; i++) {
        const item = dt.items[i];
        if (item.kind !== 'file') {continue;}
        const file = item.getAsFile();
        if (!file) {continue;}
        if (file.type.startsWith('image/')) {
          imageFiles.push(file);
        } else {
          otherFiles.push(file);
        }
      }

      const allFiles = [...otherFiles, ...imageFiles];
      if (allFiles.length === 0) {return;}

      // Office apps (Excel/WPS/Google Sheets) place both text and a rendered
      // bitmap on the clipboard. Prefer text so pasting cells inserts TSV data
      // instead of a screenshot. Only apply when ALL files are images — if the
      // user copies a real file (PDF, etc.) we always upload it.
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
    isUploadingPaste,
    handlePaste,
    handleDroppedFiles,
  };
};
