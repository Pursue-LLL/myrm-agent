/**
 * [INPUT]
 * - ./SendFailedNotice::SendFailedNotice (POS: Failed-send line of a user bubble)
 * - ./UserMessageAttachments::HistoryImageItem, FileContentBlock (POS: Attachment previews of a sent user bubble)
 * - ./QuoteToolbar::QuoteToolbar, useQuoteSelection (POS: Text-selection toolbar of a message)
 * - @/lib/utils/messageUtils (POS: Message text cleanup helpers, explicit skill activation wire format)
 * - @/lib/utils/urlUtils::splitTextWithAtLinks (POS: URL helpers, splits message text at @links)
 *
 * [OUTPUT]
 * - UserMessage: one user bubble with attachments, copy, inline edit, rewind, fork and the retry line of a failed send.
 *
 * [POS]
 * Renders one user message of the transcript. Edit submit and retry are handed to the caller through callbacks.
 */
import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { Copy, Check, Pencil } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { stripUserMessageDisplayText, parseExplicitSkillActivation } from '@/lib/utils/messageUtils';
import { SkillActivationChips } from './SkillActivationChips';
import { SendFailedNotice } from './SendFailedNotice';
import { HistoryImageItem, FileContentBlock } from './UserMessageAttachments';
import { splitTextWithAtLinks } from '@/lib/utils/urlUtils';
import { File as FileType } from '@/store/chat/types';
import { isImageFile } from '@/lib/utils/fileUtils';
import { useLocale, useTranslations } from 'next-intl';
import { localizeReactNode } from '@/lib/utils/locale';
import { QuoteToolbar, useQuoteSelection } from './QuoteToolbar';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { formatMessageTimestamp } from '@/lib/utils/timeUtils';
import { isImeComposing } from '@/lib/utils/imeUtils';
import { ImageLightbox } from '../message-input-actions/ImageLightbox';
import { ForkButton } from '../chat-window/ForkButton';
import { RewindButton } from '../chat-window/RewindButton';

interface UserMessageProps {
  content: string;
  messageId: string;
  chatId?: string;
  messageIndex?: number;
  isFirst: boolean;
  createdAt?: Date;
  isEditing?: boolean;
  isLoading?: boolean;
  continuityBlocked?: boolean;
  onEdit?: () => void;
  onEditSubmit?: (newContent: string) => void;
  onCancelEdit?: () => void;
  onRetry?: () => void;
  sendFailed?: boolean;
  files?: FileType[];
}

const EDIT_TEXTAREA_MAX_HEIGHT = 300;

const UserMessage = React.memo(
  ({
    content,
    messageId,
    chatId,
    messageIndex,
    isFirst,
    createdAt,
    isEditing,
    isLoading,
    continuityBlocked = false,
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

    const skillActivation = useMemo(() => parseExplicitSkillActivation(content), [content]);
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
          if (isImeComposing(e) || isLoading) {
            return;
          }
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
      <>
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
                {skillActivation ? (
                  <SkillActivationChips
                    skillNames={skillActivation.skillNames}
                    instruction={skillActivation.instruction}
                    className="mb-2 lg:w-9/12"
                  />
                ) : null}
                <h2
                  className={cn(
                    'font-medium text-2xl lg:w-9/12 flex-1',
                    sendFailed ? 'text-destructive dark:text-destructive' : 'text-black dark:text-white',
                  )}
                >
                  {parts.map((part, index) => {
                    if (part.type === 'link') {
                      const url = part.content.substring(1);
                      return (
                        <a
                          key={index}
                          href={url.startsWith('http') ? url : `https://${url}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:text-primary-hover transition-colors cursor-pointer underline decoration-2"
                        >
                          {part.content}
                        </a>
                      );
                    }
                    return <span key={index}>{part.content}</span>;
                  })}
                </h2>

                <div className="flex items-center gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity duration-200 flex-shrink-0">
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
                      disabled={continuityBlocked}
                      className="p-1.5 text-black/50 dark:text-white/50 rounded-lg hover:bg-secondary dark:hover:bg-secondary transition duration-200 hover:text-black dark:hover:text-white disabled:opacity-40 disabled:pointer-events-none"
                      title={t('message.edit')}
                    >
                      <Pencil size={16} />
                    </button>
                  )}
                  {chatId && messageIndex !== undefined && (
                    <>
                      <RewindButton
                        chatId={chatId}
                        messageId={messageId}
                        messageIndex={messageIndex}
                        disabled={continuityBlocked}
                      />
                      {!continuityBlocked && <ForkButton chatId={chatId} messageIndex={messageIndex} />}
                    </>
                  )}
                </div>
              </>
            )}
          </div>
          {!isEditing && <QuoteToolbar state={quoteState} onDismiss={dismissQuote} />}

          {sendFailed && onRetry && !isEditing && <SendFailedNotice onRetry={onRetry} />}

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
                      if (idx !== -1) {
                        setLightboxIndex(idx);
                      }
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
        </div>
      </>,
      locale,
    );
  },
);

UserMessage.displayName = 'UserMessage';

export default UserMessage;
