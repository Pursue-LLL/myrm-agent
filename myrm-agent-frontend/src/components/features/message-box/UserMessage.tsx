import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { Copy, Check, Pencil, FileText, ImageOff, RotateCw, Download } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils/classnameUtils';
import { stripUserMessageDisplayText } from '@/lib/utils/messageUtils';
import { splitTextWithAtLinks } from '@/lib/utils/urlUtils';
import { File as FileType } from '@/store/chat/types';
import { isImageFile, getDisplayUrl } from '@/lib/utils/fileUtils';
import { useLocale, useTranslations } from 'next-intl';
import { localizeReactNode } from '@/lib/utils/localeText';
import { QuoteToolbar, useQuoteSelection } from './QuoteToolbar';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { formatMessageTimestamp } from '@/lib/utils/timeUtils';
import { ImageLightbox } from '../message-input-actions/ImageLightbox';

interface UserMessageProps {
  content: string;
  messageId: string;
  isFirst: boolean;
  createdAt?: Date;
  isEditing?: boolean;
  isLoading?: boolean;
  onEdit?: () => void;
  onEditSubmit?: (newContent: string) => void;
  onCancelEdit?: () => void;
  onRetry?: () => void;
  sendFailed?: boolean;
  files?: FileType[];
}

const HistoryImageItem = ({
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

const FileContentBlock = ({ file }: { file: FileType }) => {
  const src = useMemo(() => getDisplayUrl(file), [file]);

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
      className={cn(
        'group flex items-center justify-between w-64 p-3 rounded-xl border border-border/40',
        'bg-card hover:bg-secondary/40 hover:border-primary/30',
        'transition-all duration-200 cursor-pointer flex-shrink-0',
      )}
      title={file.fileName}
    >
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
          <FileText size={20} className="text-primary" />
        </div>
        <div className="flex flex-col min-w-0">
          <span className="text-sm font-medium text-foreground truncate">{file.fileName}</span>
          <span className="text-xs text-muted-foreground uppercase">
            {file.fileExtension ? file.fileExtension.replace('.', '') : 'FILE'} Document
          </span>
        </div>
      </div>
      <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity ml-2">
        <button
          onClick={handleDownload}
          className="p-1.5 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-full transition-colors"
          title="Download"
        >
          <Download size={16} />
        </button>
      </div>
    </div>
  );
};

const EDIT_TEXTAREA_MAX_HEIGHT = 300;

const UserMessage = React.memo(
  ({
    content,
    messageId,
    isFirst,
    createdAt,
    isEditing,
    isLoading,
    onEdit,
    onEditSubmit,
    onCancelEdit,
    onRetry,
    sendFailed,
    files,
  }: UserMessageProps) => {
    const [copied, setCopied] = useState(false);
    const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
    const [editText, setEditText] = useState('');
    const editTextareaRef = useRef<HTMLTextAreaElement>(null);
    const contentRef = useRef<HTMLDivElement>(null);
    const { state: quoteState, dismiss: dismissQuote } = useQuoteSelection(contentRef);
    const locale = useLocale();
    const t = useTranslations('chat');

    const timestamp = useMemo(
      () => (createdAt ? formatMessageTimestamp(createdAt, locale, t('dateGroup.yesterday')) : null),
      [createdAt, locale, t],
    );

    const cleanContent = stripUserMessageDisplayText(content);
    const parts = splitTextWithAtLinks(cleanContent);

    useEffect(() => {
      if (isEditing) {
        setEditText(cleanContent);
        requestAnimationFrame(() => {
          const ta = editTextareaRef.current;
          if (ta) {
            ta.style.height = 'auto';
            ta.style.height = `${Math.min(ta.scrollHeight, EDIT_TEXTAREA_MAX_HEIGHT)}px`;
            ta.focus();
            ta.setSelectionRange(ta.value.length, ta.value.length);
          }
        });
      }
    }, [isEditing, cleanContent]);

    const handleAutoResize = useCallback((target: HTMLTextAreaElement) => {
      target.style.height = 'auto';
      target.style.height = `${Math.min(target.scrollHeight, EDIT_TEXTAREA_MAX_HEIGHT)}px`;
    }, []);

    const handleEditKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          onCancelEdit?.();
          return;
        }
        if (e.key === 'Enter' && !e.shiftKey) {
          if (e.nativeEvent.isComposing || isLoading) return;
          e.preventDefault();
          const trimmed = editText.trim();
          if (trimmed && onEditSubmit) {
            onEditSubmit(trimmed);
          }
        }
      },
      [editText, isLoading, onEditSubmit, onCancelEdit],
    );

    const handleSubmitEdit = useCallback(() => {
      const trimmed = editText.trim();
      if (trimmed && onEditSubmit) {
        onEditSubmit(trimmed);
      }
    }, [editText, onEditSubmit]);

    const handleCopy = useCallback(() => {
      writeToClipboard(cleanContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 1000);
    }, [cleanContent]);

    const imageFiles = useMemo(() => files?.filter((f) => isImageFile(f.fileExtension)) || [], [files]);

    return localizeReactNode(
      <div className={cn('w-full group', isFirst ? 'pt-16' : 'pt-8', 'break-words')}>
        <div ref={contentRef} data-message-id={messageId} className="flex items-start gap-3">
          {isEditing ? (
            <div className="flex-1 lg:w-9/12">
              <textarea
                ref={editTextareaRef}
                value={editText}
                onChange={(e) => {
                  setEditText(e.target.value);
                  handleAutoResize(e.target);
                }}
                onKeyDown={handleEditKeyDown}
                className={cn(
                  'w-full resize-none rounded-xl border border-primary/30 bg-background px-4 py-3',
                  'text-base text-foreground placeholder:text-muted-foreground',
                  'focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/50',
                  'transition-all duration-200',
                )}
                style={{ maxHeight: EDIT_TEXTAREA_MAX_HEIGHT, overflowY: 'auto' }}
              />
              <div className="flex items-center gap-2 mt-2">
                <button
                  onClick={handleSubmitEdit}
                  disabled={!editText.trim() || isLoading}
                  className={cn(
                    'px-4 py-1.5 text-sm font-medium rounded-lg transition-colors',
                    editText.trim() && !isLoading
                      ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                      : 'bg-muted text-muted-foreground cursor-not-allowed',
                  )}
                >
                  {t('editSubmit')}
                </button>
                <button
                  onClick={onCancelEdit}
                  className="px-4 py-1.5 text-sm font-medium rounded-lg text-muted-foreground hover:bg-secondary transition-colors"
                >
                  {t('cancel')}
                </button>
              </div>
            </div>
          ) : (
            <>
              <h2
                className={cn(
                  'font-medium text-2xl lg:w-9/12 flex-1',
                  sendFailed ? 'text-destructive dark:text-destructive' : 'text-black dark:text-white',
                )}
              >
                {parts.map((part, index) => {
                  if (part.type === 'link') {
                    return (
                      <span
                        key={index}
                        className="text-primary hover:text-primary-hover transition-colors cursor-pointer underline decoration-2"
                        onClick={() => {
                          const url = part.content.substring(1);
                          const fullUrl = url.startsWith('http') ? url : `https://${url}`;
                          window.open(fullUrl, '_blank', 'noopener,noreferrer');
                        }}
                      >
                        {part.content}
                      </span>
                    );
                  }
                  return <span key={index}>{part.content}</span>;
                })}
              </h2>

              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex-shrink-0">
                {timestamp && (
                  <span className="text-xs text-muted-foreground/60 mr-1 select-none" title={timestamp.title}>
                    {timestamp.label}
                  </span>
                )}
                <button
                  onClick={handleCopy}
                  className="p-1.5 text-black/50 dark:text-white/50 rounded-lg hover:bg-secondary dark:hover:bg-secondary transition duration-200 hover:text-black dark:hover:text-white"
                  title="复制 / Copy"
                >
                  {copied ? <Check size={16} /> : <Copy size={16} />}
                </button>
                {onEdit && (
                  <button
                    onClick={onEdit}
                    className="p-1.5 text-black/50 dark:text-white/50 rounded-lg hover:bg-secondary dark:hover:bg-secondary transition duration-200 hover:text-black dark:hover:text-white"
                    title="编辑 / Edit"
                  >
                    <Pencil size={16} />
                  </button>
                )}
              </div>
            </>
          )}
        </div>
        {!isEditing && <QuoteToolbar state={quoteState} onDismiss={dismissQuote} />}

        {sendFailed && onRetry && !isEditing && (
          <div className="mt-2 flex items-center gap-2">
            <span className="text-sm text-destructive/80">{t('messageFailed.networkError')}</span>
            <button
              onClick={onRetry}
              className="inline-flex items-center gap-1.5 px-3 py-1 text-sm font-medium rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
            >
              <RotateCw size={14} />
              {t('retry')}
            </button>
          </div>
        )}

        {files && files.length > 0 && (
          <div className="flex gap-2.5 mt-3 overflow-x-auto scrollbar-hide items-end">
            {files.map((file) =>
              isImageFile(file.fileExtension) ? (
                <HistoryImageItem
                  key={file.fileName}
                  file={file}
                  messageId={messageId}
                  onPreview={() => {
                    const idx = imageFiles.findIndex((f) => f.fileName === file.fileName);
                    if (idx !== -1) setLightboxIndex(idx);
                  }}
                />
              ) : (
                <FileContentBlock key={file.fileName} file={file} />
              ),
            )}
          </div>
        )}

        {lightboxIndex !== null && (
          <ImageLightbox
            images={imageFiles}
            initialIndex={lightboxIndex}
            onClose={() => setLightboxIndex(null)}
            layoutIdPrefix={`${messageId}-`}
          />
        )}
      </div>,
      locale,
    );
  },
);

UserMessage.displayName = 'UserMessage';

export default UserMessage;
