'use client';

import { useEffect, useState } from 'react';
import { X, ChevronDown, ChevronUp } from 'lucide-react';
import { type FlowPadCapture } from '@/store/useFlowPadStore';

const MAX_TEXT_PER_CAPTURE = 4000;
const MAX_PREVIEW_TEXT = 200;

export function formatAppshotMessage(captures: FlowPadCapture[]): string {
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

export function CapturePreview({
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

export function ImageLightbox({
  src,
  alt,
  onClose,
}: {
  src: string;
  alt: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', handleEsc, true);
    return () => document.removeEventListener('keydown', handleEsc, true);
  }, [onClose]);

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

