import { FileText, FileSpreadsheet, Trash2, X, ImageOff, Play, Pencil } from 'lucide-react';
import { File as FileType } from '@/store/useChatStore';
import { isImageFile, isVideoFile, isPdfFile, getDisplayUrl } from '@/lib/utils/fileUtils';
import { useMemo, useRef, useState, useEffect, lazy, Suspense } from 'react';
import { motion } from 'framer-motion';
import { ImageLightbox } from './ImageLightbox';

const AnnotationEditor = lazy(() => import('@/components/features/annotation-editor/AnnotationEditor'));

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
      {onEdit && (
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
          className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-foreground/80 text-background flex items-center justify-center opacity-60 hover:opacity-100 transition-opacity z-10"
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
  const src = useMemo(() => getDisplayUrl(file), [file]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) return;
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
      {ready && (
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
          className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-foreground/80 text-background flex items-center justify-center opacity-60 hover:opacity-100 transition-opacity z-10"
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
  return <FileText size={12} className="text-muted-foreground" />;
};

export const FilePill = ({ file, onRemove }: { file: FileType; onRemove?: () => void }) => (
  <div className="flex items-center gap-2 p-2 bg-secondary rounded-full border border-border/50 min-w-0 flex-shrink-0">
    <div className="flex-shrink-0 bg-muted flex items-center justify-center w-6 h-6 rounded-sm">
      {getFileIcon(file.fileExtension)}
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

const AttachList: React.FC<AttachListProps> = ({
  files,
  setFiles,
  clearCurrentSessionMessageId,
  setHideAttachList,
}) => {
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [editingFile, setEditingFile] = useState<FileType | null>(null);

  const handleRemoveFile = (filename: string) => {
    const newFiles = files.filter((f) => f.fileName !== filename);
    setFiles(newFiles);
    if (newFiles.length === 0) {
      clearCurrentSessionMessageId();
      setHideAttachList?.(false);
    }
  };

  const handleAnnotationSave = (result: { dataUrl: string; textAnnotations: string[] }) => {
    if (!editingFile) return;
    const updatedFiles = files.map((f) =>
      f.fileName === editingFile.fileName ? { ...f, fileUrl: result.dataUrl, fileExtension: 'png' } : f,
    );
    setFiles(updatedFiles);
    setEditingFile(null);
  };

  if (files.length === 0) return null;

  const imageFiles = files.filter((file) => isImageFile(file.fileExtension));

  return (
    <>
      <div className="flex gap-2 overflow-x-auto scrollbar-hide pt-2 pb-2 items-end">
        {files.map((file) => {
          if (isImageFile(file.fileExtension)) {
            return (
              <ImageThumbnail
                key={file.fileName}
                file={file}
                onRemove={() => handleRemoveFile(file.fileName)}
                onClick={() => {
                  const index = imageFiles.findIndex((f) => f.fileName === file.fileName);
                  if (index !== -1) {
                    setLightboxIndex(index);
                  }
                }}
                onEdit={() => setEditingFile(file)}
              />
            );
          }
          if (isVideoFile(file.fileExtension)) {
            return <VideoThumbnail key={file.fileName} file={file} onRemove={() => handleRemoveFile(file.fileName)} />;
          }
          return <FilePill key={file.fileName} file={file} onRemove={() => handleRemoveFile(file.fileName)} />;
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
          <AnnotationEditor
            imageSrc={getDisplayUrl(editingFile) || ''}
            onSave={handleAnnotationSave}
            onClose={() => setEditingFile(null)}
          />
        </Suspense>
      )}
    </>
  );
};

export default AttachList;
