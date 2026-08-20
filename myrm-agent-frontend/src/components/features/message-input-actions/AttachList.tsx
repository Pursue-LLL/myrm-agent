import { FileText, FileSpreadsheet, Trash2, X, ImageOff, Play, Pencil, Music, LoaderCircle, AlertCircle } from 'lucide-react';
import { File as FileType } from '@/store/useChatStore';
import { isImageFile, isVideoFile, isAudioFile, isPdfFile, getDisplayUrl } from '@/lib/utils/fileUtils';
import { useMemo, useRef, useState, useEffect, lazy, Suspense, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { motion } from 'framer-motion';
import { toast } from '@/hooks/shared/useToast';
import { ImageLightbox } from './ImageLightbox';
import { blobToDataUrl } from '@/components/features/image-editor/uploadAnnotated';

const ImageEditor = lazy(() => import('@/components/features/image-editor/ImageEditor'));

interface AttachListProps {
  files: FileType[];
  setFiles: (files: FileType[]) => void;
  clearCurrentSessionMessageId: () => void;
  setHideAttachList?: (hide: boolean) => void;
}

export const ImageThumbnail = ({
  file,
  onRemove,
  onClick,
  onEdit,
}: {
  file: FileType;
  onRemove?: () => void;
  onClick?: () => void;
  onEdit?: () => void;
}) => {
  const [loadFailed, setLoadFailed] = useState(false);
  const isUploading = file.status === 'uploading';
  const isError = file.status === 'error';

  const src = useMemo(() => getDisplayUrl(file), [file]);

  if (!src || loadFailed) {
    return (
      <div
        className="relative group flex-shrink-0 w-16 h-16 rounded-lg border border-border/50 bg-muted flex items-center justify-center"
        title={file.fileName}
      >
        <ImageOff size={16} className="text-muted-foreground" />
        {onRemove && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
            className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-foreground/80 text-background flex items-center justify-center opacity-60 hover:opacity-100 transition-opacity z-10"
          >
            <X size={10} />
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="relative group flex-shrink-0 w-16 h-16" title={file.fileName}>
      <motion.img
        layoutId={`image-input-${file.fileName}`}
        src={src}
        alt={file.fileName}
        onError={() => setLoadFailed(true)}
        onClick={onClick}
        className="w-full h-full object-cover rounded-lg border border-border/50 cursor-pointer hover:opacity-90 transition-opacity"
      />
      {/* 正在上传状态罩与进度 */}
      {isUploading && (
        <div className="absolute inset-0 rounded-lg bg-black/40 backdrop-blur-[1px] flex flex-col items-center justify-center pointer-events-none z-10">
          <LoaderCircle size={14} className="text-white animate-spin mb-0.5" />
          {typeof file.uploadPercent === 'number' && file.uploadPercent > 0 && (
            <span className="text-[9px] font-medium text-white tabular-nums leading-none">
              {file.uploadPercent}%
            </span>
          )}
        </div>
      )}
      {/* 上传失败错误标 */}
      {isError && (
        <div className="absolute inset-0 rounded-lg bg-destructive/30 backdrop-blur-[1px] flex items-center justify-center pointer-events-none z-10">
          <AlertCircle size={16} className="text-destructive-foreground" />
        </div>
      )}
      {onEdit && !isUploading && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onEdit();
          }}
          className="absolute bottom-0.5 left-0.5 w-5 h-5 rounded-full bg-primary/90 text-primary-foreground flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity z-10"
          title="Edit"
        >
          <Pencil size={10} />
        </button>
      )}
      {onRemove && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-foreground/80 text-background flex items-center justify-center opacity-60 hover:opacity-100 transition-opacity z-20"
        >
          <X size={10} />
        </button>
      )}
    </div>
  );
};

export const VideoThumbnail = ({ file, onRemove }: { file: FileType; onRemove?: () => void }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  const isUploading = file.status === 'uploading';
  const isError = file.status === 'error';
  const src = useMemo(() => getDisplayUrl(file), [file]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) {return;}
    const handleLoaded = () => setReady(true);
    video.addEventListener('loadeddata', handleLoaded);
    video.currentTime = 0.5;
    return () => video.removeEventListener('loadeddata', handleLoaded);
  }, [src]);

  return (
    <div className="relative group flex-shrink-0 w-16 h-16" title={file.fileName}>
      {src ? (
        <video
          ref={videoRef}
          src={src}
          muted
          preload="metadata"
          className="w-full h-full object-cover rounded-lg border border-border/50"
        />
      ) : (
        <div className="w-full h-full rounded-lg border border-border/50 bg-muted" />
      )}
      {isUploading && (
        <div className="absolute inset-0 rounded-lg bg-black/40 backdrop-blur-[1px] flex flex-col items-center justify-center pointer-events-none z-10">
          <LoaderCircle size={14} className="text-white animate-spin mb-0.5" />
          {typeof file.uploadPercent === 'number' && file.uploadPercent > 0 && (
            <span className="text-[9px] font-medium text-white tabular-nums leading-none">
              {file.uploadPercent}%
            </span>
          )}
        </div>
      )}
      {isError && (
        <div className="absolute inset-0 rounded-lg bg-destructive/30 backdrop-blur-[1px] flex items-center justify-center pointer-events-none z-10">
          <AlertCircle size={16} className="text-destructive-foreground" />
        </div>
      )}
      {!isUploading && ready && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-5 h-5 rounded-full bg-black/60 flex items-center justify-center">
            <Play size={10} className="text-white ml-0.5" fill="currentColor" />
          </div>
        </div>
      )}
      {onRemove && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-foreground/80 text-background flex items-center justify-center opacity-60 hover:opacity-100 transition-opacity z-20"
        >
          <X size={10} />
        </button>
      )}
    </div>
  );
};

const getFileIcon = (ext: string) => {
  const lower = ext.toLowerCase();
  if (lower === 'xlsx' || lower === 'xls' || lower === 'csv') {
    return <FileSpreadsheet size={12} className="text-green-600 dark:text-green-400" />;
  }
  if (lower === 'docx') {
    return <FileText size={12} className="text-blue-600 dark:text-blue-400" />;
  }
  if (isPdfFile(lower)) {
    return <FileText size={12} className="text-red-600 dark:text-red-400" />;
  }
  if (isAudioFile(lower)) {
    return <Music size={12} className="text-purple-600 dark:text-purple-400" />;
  }
  return <FileText size={12} className="text-muted-foreground" />;
};

export const FilePill = ({ file, onRemove }: { file: FileType; onRemove?: () => void }) => {
  const isUploading = file.status === 'uploading';
  const isError = file.status === 'error';

  return (
    <div className="flex items-center gap-2 p-2 bg-secondary rounded-full border border-border/50 min-w-0 flex-shrink-0">
      <div className="flex-shrink-0 bg-muted flex items-center justify-center w-6 h-6 rounded-sm">
        {isUploading ? (
          <LoaderCircle size={12} className="text-primary animate-spin" />
        ) : isError ? (
          <AlertCircle size={12} className="text-destructive" />
        ) : (
          getFileIcon(file.fileExtension)
        )}
      </div>
      <div className="flex-1 min-w-0 max-w-32">
        <p className="text-xs text-foreground truncate" title={file.fileName || ''}>
          {file.fileName || ''}
        </p>
      </div>
      {onRemove && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="flex-shrink-0 p-0.5 text-muted-foreground hover:text-foreground transition-colors"
        >
          <Trash2 size={12} />
        </button>
      )}
    </div>
  );
};

const AttachList: React.FC<AttachListProps> = ({
  files,
  setFiles,
  clearCurrentSessionMessageId,
  setHideAttachList,
}) => {
  const tEditor = useTranslations('imageEditor');
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [editingFile, setEditingFile] = useState<FileType | null>(null);

  const handleRemoveFile = (targetFile: FileType) => {
    if (targetFile.previewUrl) {
      URL.revokeObjectURL(targetFile.previewUrl);
    }
    const newFiles = files.filter(
      (f) => (targetFile.tempId ? f.tempId !== targetFile.tempId : f.fileName !== targetFile.fileName),
    );
    setFiles(newFiles);
    if (newFiles.length === 0) {
      clearCurrentSessionMessageId();
      setHideAttachList?.(false);
    }
  };

  const handleAnnotationComplete = useCallback(
    async (blob: Blob) => {
      if (!editingFile) {return;}
      try {
        const dataUrl = await blobToDataUrl(blob);
        const updatedFiles = files.map((f) =>
          f.fileName === editingFile.fileName ? { ...f, fileUrl: dataUrl, fileExtension: 'png', status: 'ready' as const } : f,
        );
        setFiles(updatedFiles);
        setEditingFile(null);
      } catch (err) {
        console.error('Failed to apply annotated image:', err);
        toast({
          title: tEditor('applyFailedTitle'),
          description: tEditor('applyFailedDesc'),
        });
      }
    },
    [editingFile, files, setFiles, tEditor],
  );

  if (files.length === 0) {return null;}

  const imageFiles = files.filter((file) => isImageFile(file.fileExtension));

  return (
    <>
      <div className="flex gap-2 overflow-x-auto scrollbar-hide pt-2 pb-2 items-end">
        {files.map((file) => {
          const key = file.tempId || file.fileName;
          if (isImageFile(file.fileExtension)) {
            return (
              <ImageThumbnail
                key={key}
                file={file}
                onRemove={() => handleRemoveFile(file)}
                onClick={() => {
                  const index = imageFiles.findIndex((f) => (file.tempId ? f.tempId === file.tempId : f.fileName === file.fileName));
                  if (index !== -1) {
                    setLightboxIndex(index);
                  }
                }}
                onEdit={() => setEditingFile(file)}
              />
            );
          }
          if (isVideoFile(file.fileExtension)) {
            return <VideoThumbnail key={key} file={file} onRemove={() => handleRemoveFile(file)} />;
          }
          return <FilePill key={key} file={file} onRemove={() => handleRemoveFile(file)} />;
        })}
      </div>

      {lightboxIndex !== null && (
        <ImageLightbox
          images={imageFiles}
          initialIndex={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          layoutIdPrefix="input-"
        />
      )}

      {editingFile && (
        <Suspense fallback={null}>
          <ImageEditor
            imageSrc={getDisplayUrl(editingFile) || ''}
            onComplete={handleAnnotationComplete}
            onCancel={() => setEditingFile(null)}
          />
        </Suspense>
      )}
    </>
  );
};

export default AttachList;
