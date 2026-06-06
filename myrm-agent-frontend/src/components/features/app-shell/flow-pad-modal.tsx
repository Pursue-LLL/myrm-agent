'use client';

/**
 * [INPUT]
 * - useFlowPadStore (POS: FlowPad 全局状态)
 * - useChatStore (POS: 消息发送)
 *
 * [OUTPUT]
 * - FlowPadModal: 全局居中 Dialog，整合截图预览 + 指令输入
 *
 * [POS]
 * Omni-FlowPad 核心 UI 组件。全局居中 Dialog，
 * 同时服务 Appshot 截屏和 deep link Quick Ask 场景。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Dialog, DialogContent, DialogTitle } from '@/components/primitives/dialog';
import { useFlowPadStore, type FlowPadCapture } from '@/store/useFlowPadStore';
import useChatStore from '@/store/useChatStore';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import { cn } from '@/lib/utils/classnameUtils';
import { Send, X, ChevronDown, ChevronUp, Monitor } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';

const MAX_TEXT_PER_CAPTURE = 4000;
const MAX_PREVIEW_TEXT = 200;

function formatAppshotMessage(captures: FlowPadCapture[]): string {
  if (captures.length === 0) return '';

  const parts: string[] = ['[Appshot Context]'];

  for (const cap of captures) {
    const header = cap.windowTitle ? `**${cap.windowTitle}**` : 'Screen Capture';
    parts.push(`\n---\n${header}`);
    if (cap.extractedText.trim()) {
      const truncated =
        cap.extractedText.length > MAX_TEXT_PER_CAPTURE
          ? cap.extractedText.slice(0, MAX_TEXT_PER_CAPTURE) + '\n...(truncated)'
          : cap.extractedText;
      parts.push(`\`\`\`\n${truncated}\n\`\`\``);
    }
  }

  return parts.join('\n');
}

function CapturePreview({
  capture,
  onImageClick,
  onRemove,
  collapseLabel,
}: {
  capture: FlowPadCapture;
  onImageClick: () => void;
  onRemove: () => void;
  collapseLabel: string;
}) {
  const [textExpanded, setTextExpanded] = useState(false);
  const hasText = capture.extractedText.trim().length > 0;
  const previewText =
    capture.extractedText.length > MAX_PREVIEW_TEXT
      ? capture.extractedText.slice(0, MAX_PREVIEW_TEXT) + '...'
      : capture.extractedText;

  return (
    <div className="flex-shrink-0 w-[200px] rounded-lg border border-border/50 overflow-hidden bg-muted/20 relative group">
      <button
        type="button"
        onClick={onRemove}
        className="absolute top-1 right-1 z-10 h-5 w-5 rounded-full bg-black/60 text-white/80 hover:bg-black/80 hover:text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <X className="w-3 h-3" />
      </button>
      {capture.screenshot && (
        <button
          type="button"
          onClick={onImageClick}
          className="w-full aspect-video bg-black/5 dark:bg-white/5 cursor-pointer hover:opacity-80 transition-opacity"
        >
          <img
            src={`data:image/jpeg;base64,${capture.screenshot}`}
            alt={capture.windowTitle || 'Screen capture'}
            className="w-full h-full object-cover"
          />
        </button>
      )}
      {capture.windowTitle && (
        <div className="px-2 py-1 text-[10px] font-medium text-muted-foreground truncate border-t border-border/30">
          {capture.windowTitle}
        </div>
      )}
      {hasText && (
        <button
          type="button"
          onClick={() => setTextExpanded(!textExpanded)}
          className="w-full px-2 py-1 text-[10px] text-muted-foreground/70 flex items-center gap-1 hover:text-muted-foreground transition-colors border-t border-border/20"
        >
          {textExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          <span className="truncate">{textExpanded ? collapseLabel : previewText}</span>
        </button>
      )}
      {hasText && textExpanded && (
        <div className="px-2 py-1 text-[10px] text-muted-foreground/60 max-h-24 overflow-y-auto whitespace-pre-wrap break-words border-t border-border/20">
          {capture.extractedText}
        </div>
      )}
    </div>
  );
}

function ImageLightbox({
  src,
  alt,
  onClose,
}: {
  src: string;
  alt: string;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-[300] flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <button type="button" className="absolute top-4 right-4 text-white/80 hover:text-white" onClick={onClose}>
        <X className="w-6 h-6" />
      </button>
      <img
        src={src}
        alt={alt}
        className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}

export function FlowPadModal() {
  const t = useTranslations('flowPad');
  const { isOpen, captures, initialText, close, removeCapture } = useFlowPadStore();
  const { agentConfig, sendMessage, setFiles } = useChatStore();

  const [text, setText] = useState('');
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const autoResizeTextarea = useCallback(() => {
    const el = inputRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = el.scrollHeight + 'px';
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      setText(initialText);
      setLightboxSrc(null);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen, initialText]);

  useEffect(() => {
    autoResizeTextarea();
  }, [text, autoResizeTextarea]);

  const handleSubmit = useCallback(async () => {
    const hasCaptures = captures.length > 0;
    const hasText = text.trim().length > 0;

    if (!hasCaptures && !hasText) return;
    if (isSubmitting) return;

    setIsSubmitting(true);
    try {
      if (hasCaptures) {
        const screenshotFiles = captures
          .filter((c) => c.screenshot)
          .map((c, idx) => ({
            fileName: `appshot_${idx + 1}.jpg`,
            fileExtension: 'jpg',
            fileUrl: `data:image/jpeg;base64,${c.screenshot}`,
            fileType: 'uploaded' as const,
          }));

        if (screenshotFiles.length > 0) {
          const currentFiles = useChatStore.getState().files;
          setFiles([...currentFiles, ...screenshotFiles]);
        }
      }

      const parts: string[] = [];
      if (hasCaptures) {
        parts.push(formatAppshotMessage(captures));
      }
      if (hasText) {
        parts.push(text.trim());
      }

      const message = parts.join('\n\n');
      if (message) {
        await sendMessage(message);
      }

      const agentLabel = agentConfig?.name || t('defaultAgent');
      toast.success(t('submitted', { agent: agentLabel }), { duration: 3000 });
      close();
    } catch (err) {
      console.error('FlowPad submit failed:', err);
      toast.error(t('submitFailed'), { duration: 3000 });
    } finally {
      setIsSubmitting(false);
    }
  }, [captures, text, setFiles, sendMessage, close, agentConfig, t, isSubmitting]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.nativeEvent.isComposing) return;

      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const hasCaptures = captures.length > 0;

  return (
    <>
      <Dialog open={isOpen} onOpenChange={(open) => !open && close()}>
        <DialogContent className="sm:max-w-[640px] p-0 overflow-hidden bg-background/90 backdrop-blur-xl border-border/50 shadow-2xl gap-0 [&>button.absolute]:hidden">
          <VisuallyHidden>
            <DialogTitle>{t('title')}</DialogTitle>
          </VisuallyHidden>

          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/40 bg-muted/20">
            <div className="flex items-center gap-2">
              <Monitor className="w-3.5 h-3.5 text-muted-foreground/70" />
              <span className="text-xs font-medium text-muted-foreground">
                {hasCaptures ? t('titleWithCapture') : t('title')}
              </span>
            </div>
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={close}>
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>

          {/* Captures Preview */}
          {hasCaptures && (
            <div className="px-4 py-3 border-b border-border/30 bg-muted/10">
              <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin">
                {captures.map((capture, idx) => (
                  <CapturePreview
                    key={capture.timestamp + idx}
                    capture={capture}
                    collapseLabel={t('collapse')}
                    onRemove={() => removeCapture(idx)}
                    onImageClick={() =>
                      capture.screenshot && setLightboxSrc(`data:image/jpeg;base64,${capture.screenshot}`)
                    }
                  />
                ))}
              </div>
            </div>
          )}

          {/* Agent indicator */}
          {agentConfig?.name && (
            <div className="px-4 py-1.5 border-b border-border/20 bg-muted/5">
              <span className="text-[10px] text-muted-foreground/60">
                {t('sendTo')}{' '}
                <span className="font-medium text-muted-foreground">{agentConfig.name}</span>
              </span>
            </div>
          )}

          {/* Input */}
          <div className="p-4 relative">
            <textarea
              ref={inputRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={hasCaptures ? t('placeholderWithCapture') : t('placeholder')}
              className={cn(
                'w-full resize-none border-0 focus:outline-none focus-visible:ring-0',
                'text-base bg-transparent placeholder:text-muted-foreground/40',
                'min-h-[80px] max-h-[200px]',
              )}
              rows={3}
            />
            <div className="flex items-center justify-end gap-2 mt-2">
              <span className="text-[10px] text-muted-foreground/40">
                Enter {t('toSend')} · Esc {t('toCancel')}
              </span>
              <Button
                size="icon"
                className="h-8 w-8 rounded-full"
                onClick={handleSubmit}
                disabled={isSubmitting || (!text.trim() && !hasCaptures)}
              >
                {isSubmitting ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {lightboxSrc && (
        <ImageLightbox src={lightboxSrc} alt="Appshot" onClose={() => setLightboxSrc(null)} />
      )}
    </>
  );
}
