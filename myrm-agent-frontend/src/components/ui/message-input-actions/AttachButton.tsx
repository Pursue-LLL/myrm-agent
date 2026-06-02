import { cn } from '@/lib/utils/classnameUtils';
import { Paperclip, LoaderCircle } from 'lucide-react';
import { useRef, useState } from 'react';
import { File as FileType } from '@/store/useChatStore';
import { useTranslations } from 'next-intl';
import Tooltip from '@/components/ui/settings/Tooltip';
import { toast } from '@/hooks/useToast';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { selectFiles, toStoreFile, getFileService } from '@/services/file-service';
import { computeFileHash, isImageFile, isVideoFile, getFileExtension } from '@/lib/utils/fileUtils';
import useProviderStore from '@/store/useProviderStore';
import { resetUploadController, getUploadSignal } from '@/services/uploadController';

const MAX_VIDEO_BYTES = 100 * 1024 * 1024; // 100MB — aligned with backend VideoAnalysisEngine limit

const AttachButton = ({ files, setFiles }: { files: FileType[]; setFiles: (files: FileType[]) => void }) => {
  const t = useTranslations('files');
  const [loading, setLoading] = useState(false);
  const [uploadPercent, setUploadPercent] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  /**
   * Check if current model supports vision/video (required for image/video uploads).
   * PDFs are always allowed — backend extracts text or renders images as needed.
   * Videos are allowed when the model supports video natively or a vision fallback is configured.
   */
  const checkModelCapability = (fileNames: string[]): string | null => {
    const { defaultModelConfig, getModelInfo } = useProviderStore.getState();
    const selection = defaultModelConfig?.baseModel?.primary;
    if (!selection) return null;

    const modelInfo = getModelInfo(selection.providerId, selection.model);
    const hasImages = fileNames.some((n) => isImageFile(getFileExtension(n)));
    const hasVideos = fileNames.some((n) => isVideoFile(getFileExtension(n)));

    const fallbackSelection = defaultModelConfig?.visionFallbackModel;
    const fallbackModelInfo = fallbackSelection
      ? getModelInfo(fallbackSelection.providerId, fallbackSelection.model)
      : null;
    const hasVisionFallback = fallbackModelInfo?.supports_vision;

    if (hasImages && !modelInfo?.supports_vision && !hasVisionFallback) {
      return 'modelNotSupportVision';
    }
    if (hasVideos && !modelInfo?.supports_video_input && !hasVisionFallback) {
      return 'modelNotSupportVideo';
    }
    return null;
  };

  // Tauri 桌面端：本地文件选择
  const handleTauriFileSelect = async () => {
    setLoading(true);
    try {
      // 使用新的 file-service 统一接口
      const selectedFiles = await selectFiles();

      if (selectedFiles.length === 0) {
        return;
      }

      const capErr = checkModelCapability(selectedFiles.map((f) => f.fileName));
      if (capErr) {
        toast({ title: t(capErr), duration: 5000 });
        return;
      }

      const existingFileNames = files.map((file) => file.fileName);
      const duplicateFiles = selectedFiles.filter((file) => existingFileNames.includes(file.fileName));

      if (duplicateFiles.length > 0) {
        toast({
          title: t('duplicateFiles'),
          description: t('duplicateFilesDesc', { names: duplicateFiles.map((f) => f.fileName).join(', ') }),
        });
        return;
      }

      if (files.length + selectedFiles.length > 5) {
        toast({
          title: t('uploadLimit'),
          description: t('uploadLimitDesc', { count: String(files.length) }),
        });
        return;
      }

      // 转换为 store 格式并添加
      const storeFiles = selectedFiles.map(toStoreFile);
      setFiles([...files, ...storeFiles]);
    } catch (error) {
      console.error('File selection failed:', error);
      toast({
        title: t('fileSelectionFailed'),
        description: error instanceof Error ? error.message : t('retryHint'),
      });
    } finally {
      setLoading(false);
    }
  };

  // Sandbox 模式：文件上传处理
  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || []);
    if (selectedFiles.length === 0) return;

    // Reset input value so the same file can be re-selected after switching models
    e.target.value = '';

    const capErr = checkModelCapability(selectedFiles.map((f) => f.name));
    if (capErr) {
      toast({ title: t(capErr), duration: 5000 });
      return;
    }

    const oversizedVideo = selectedFiles.find((f) => isVideoFile(getFileExtension(f.name)) && f.size > MAX_VIDEO_BYTES);
    if (oversizedVideo) {
      const sizeMB = `${(oversizedVideo.size / 1024 / 1024).toFixed(1)}MB`;
      toast({ title: t('videoTooLarge'), description: t('videoTooLargeDesc', { size: sizeMB }), duration: 5000 });
      return;
    }

    if (files.length + selectedFiles.length > 5) {
      toast({
        title: t('uploadLimit'),
        description: t('uploadLimitDesc', { count: String(files.length) }),
      });
      return;
    }

    setLoading(true);
    setUploadPercent(0);

    try {
      // SHA-256 去重：计算选中文件的哈希，过滤与已有文件内容相同的
      const existingHashes = new Set(files.map((f) => f.contentHash).filter(Boolean));
      const hashResults = await Promise.all(
        selectedFiles.map(async (file) => ({
          file,
          hash: await computeFileHash(file),
        })),
      );

      const duplicateNames: string[] = [];
      const filesToUpload: globalThis.File[] = [];
      const hashMap = new Map<string, string>(); // fileName -> hash

      for (const { file, hash } of hashResults) {
        if (existingHashes.has(hash)) {
          duplicateNames.push(file.name);
        } else {
          filesToUpload.push(file);
          hashMap.set(file.name, hash);
          existingHashes.add(hash);
        }
      }

      if (duplicateNames.length > 0) {
        toast({
          title: t('duplicateFiles'),
          description: duplicateNames.join(', '),
        });
      }

      if (filesToUpload.length === 0) {
        return;
      }

      resetUploadController();
      const fileService = getFileService();

      const uploadedFiles = await fileService.uploadFiles(
        filesToUpload,
        (progress) => setUploadPercent(progress.percent),
        getUploadSignal(),
      );

      if (uploadedFiles.length > 0) {
        const storeFiles = uploadedFiles.map((ref) => {
          const storeFile = toStoreFile(ref);
          storeFile.contentHash = hashMap.get(ref.fileName);
          return storeFile;
        });
        setFiles([...files, ...storeFiles]);
      } else {
        toast({
          title: t('uploadFailed'),
          description: t('unknownError'),
        });
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      console.error('File upload failed:', error);
      toast({
        title: t('uploadFailed'),
        description: error instanceof Error ? error.message : t('uploadFailedRetry'),
      });
    } finally {
      setLoading(false);
      setUploadPercent(null);
    }
  };

  return (
    <>
      {/* 添加文件按钮 */}
      {loading ? (
        <div className="flex flex-col items-center justify-center p-1.5 gap-0.5">
          <LoaderCircle size={16} className="text-black/50 dark:text-white/50 animate-spin" />
          {uploadPercent !== null && (
            <span className="text-[10px] leading-none tabular-nums text-muted-foreground">{uploadPercent}%</span>
          )}
        </div>
      ) : (
        <Tooltip content={t('attach')}>
          <button
            type="button"
            onClick={() => {
              if (isTauriRuntime()) {
                handleTauriFileSelect();
              } else {
                fileInputRef.current?.click();
              }
            }}
            className={cn(
              'flex items-center justify-center w-8 h-8 rounded-full',
              'bg-[#fdfdf8] dark:bg-muted/60',
              'transition duration-200',
              'hover:bg-[#e8e8e0] dark:hover:bg-muted/80 text-black/70 dark:text-white/70 hover:text-black dark:hover:text-white',
            )}
          >
            {!isTauriRuntime() && (
              <input
                type="file"
                onChange={handleChange}
                ref={fileInputRef}
                accept=".png,.jpeg,.jpg,.gif,.webp,.bmp,.pdf,.docx,.xlsx,.xls,.pptx,.ppt,.csv,.txt,.md,.json,.mp4,.mov,.webm,.avi,.mkv,.flv,.wmv,.m4v"
                multiple
                className="hidden"
              />
            )}
            <Paperclip size={16} />
          </button>
        </Tooltip>
      )}
    </>
  );
};

export default AttachButton;
