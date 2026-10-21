/**
 * [INPUT]
 * - @/lib/utils/fileUtils::getDisplayUrl (POS: Web/Tauri file display URL resolution)
 * - @/lib/utils/a11y::activateOnKey, REVEAL_ON_HOVER (POS: Keyboard activation for clickable non-button elements; hover/focus/touch reveal contract)
 *
 * [OUTPUT]
 * - HistoryImageItem: Thumbnail of an image attached to a sent message; falls back to a placeholder when it fails to load.
 * - FileContentBlock: Card of a non-image attachment with open-in-new-tab and download.
 *
 * [POS]
 * Attachment previews of a sent user bubble. Opening the image lightbox is left to the caller.
 */
import React, { useState, useMemo } from 'react';
import { FileText, ImageOff, Download } from 'lucide-react';
import { motion } from 'framer-motion';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { File as FileType } from '@/store/chat/types';
import { getDisplayUrl } from '@/lib/utils/fileUtils';
import { activateOnKey, REVEAL_ON_HOVER } from '@/lib/utils/a11y';

export const HistoryImageItem = ({
  file,
  messageId,
  onPreview,
}: {
  file: FileType;
  messageId: string;
  onPreview: () => void;
}) => {
  const [loadFailed, setLoadFailed] = useState(false);
  const src = useMemo(() => getDisplayUrl(file), [file]);

  if (!src || loadFailed) {
    return (
      <div
        className="flex-shrink-0 w-20 h-20 rounded-xl border border-border/40 bg-muted/50 flex items-center justify-center"
        title={file.fileName}
      >
        <ImageOff size={18} className="text-muted-foreground/60" />
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onPreview}
      className="flex-shrink-0 w-20 h-20 rounded-xl overflow-hidden border border-border/40 hover:border-primary/50 transition-all duration-200 hover:shadow-md cursor-zoom-in relative"
      title={file.fileName}
    >
      <motion.img
        layoutId={`image-${messageId}-${file.fileName}`}
        src={src}
        alt={file.fileName}
        onError={() => setLoadFailed(true)}
        className="object-cover w-full h-full"
      />
    </button>
  );
};

export const FileContentBlock = ({ file }: { file: FileType }) => {
  const t = useTranslations('chat');
  const src = useMemo(() => getDisplayUrl(file), [file]);
  const extension = file.fileExtension?.replace('.', '');

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (src) {
      const a = document.createElement('a');
      a.href = src;
      a.download = file.fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }
  };

  const handleOpen = () => {
    if (src) {
      window.open(src, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <div
      onClick={handleOpen}
      // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- clickable card with nested action buttons
      role="button"
      tabIndex={0}
      onKeyDown={activateOnKey}
      className={cn(
        'group flex items-center justify-between w-64 p-3 rounded-xl border border-border/40',
        'bg-card hover:bg-secondary/40 hover:border-primary/30',
        'transition-all duration-200 cursor-pointer flex-shrink-0',
      )}
      title={file.fileName}
      aria-label={file.fileName}
    >
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
          <FileText size={20} className="text-primary" />
        </div>
        <div className="flex flex-col min-w-0">
          <span className="text-sm font-medium text-foreground truncate">{file.fileName}</span>
          <span className="text-xs text-muted-foreground uppercase">
            {extension ? t('attachment_document', { type: extension }) : t('attachment_document_generic')}
          </span>
        </div>
      </div>
      <div className={cn('flex items-center ml-2 transition-opacity', REVEAL_ON_HOVER)}>
        <button
          onClick={handleDownload}
          className="p-1.5 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-full transition-colors"
          title={t('attachment_download')}
          aria-label={t('attachment_download')}
        >
          <Download size={16} />
        </button>
      </div>
    </div>
  );
};
