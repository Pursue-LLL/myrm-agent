'use client';

import React, { useCallback, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Send, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { BrowserRefInfo } from '@/store/chat/types';

interface SelectedElementBadgeProps {
  refId: string;
  info: BrowserRefInfo;
  onClear: () => void;
}

const SelectedElementBadge: React.FC<SelectedElementBadgeProps> = ({ refId, info, onClear }) => (
  <div className="flex items-center gap-1.5 px-2 py-1 bg-primary/10 border border-primary/30 rounded-md text-xs">
    <span className="font-mono text-primary font-medium">[@{refId}]</span>
    <span className="text-foreground truncate max-w-[150px]">
      {info.role}
      {info.name ? `: ${info.name.slice(0, 25)}` : ''}
    </span>
    <button
      type="button"
      onClick={onClear}
      className="ml-1 text-muted-foreground hover:text-foreground"
      aria-label="Clear selection"
    >
      <X className="w-3 h-3" />
    </button>
  </div>
);

interface DesktopInstructionInputProps {
  selectedRefId: string | null;
  selectedInfo: BrowserRefInfo | null;
  instructionText: string;
  onInstructionChange: (text: string) => void;
  onSubmit: (instruction: string, refId: string | null) => void;
  onClearSelection: () => void;
  disabled?: boolean;
}

const DesktopInstructionInput: React.FC<DesktopInstructionInputProps> = ({
  selectedRefId,
  selectedInfo,
  instructionText,
  onInstructionChange,
  onSubmit,
  onClearSelection,
  disabled,
}) => {
  const t = useTranslations('chat.desktopInspector');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (selectedRefId && inputRef.current) {
      inputRef.current.focus();
    }
  }, [selectedRefId]);

  const handleSubmit = useCallback(() => {
    const trimmed = instructionText.trim();
    if (!trimmed && !selectedRefId) return;
    onSubmit(trimmed, selectedRefId);
    onInstructionChange('');
  }, [instructionText, selectedRefId, onSubmit, onInstructionChange]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const hasContent = instructionText.trim().length > 0 || selectedRefId !== null;

  return (
    <div className="border-t border-border bg-background px-3 py-2">
      {selectedRefId && selectedInfo && (
        <div className="mb-2">
          <SelectedElementBadge refId={selectedRefId} info={selectedInfo} onClear={onClearSelection} />
        </div>
      )}

      <div className="flex items-end gap-2">
        <textarea
          ref={inputRef}
          value={instructionText}
          onChange={(e) => onInstructionChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={selectedRefId ? t('instructionWithElement') : t('instructionPlaceholder')}
          disabled={disabled}
          className={cn(
            'flex-1 resize-none rounded-md border border-input bg-background px-3 py-2',
            'text-sm text-foreground placeholder:text-muted-foreground',
            'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50',
            'min-h-[36px] max-h-[80px]',
            disabled && 'opacity-50 cursor-not-allowed',
          )}
          rows={1}
        />

        <button
          type="button"
          onClick={handleSubmit}
          disabled={disabled || !hasContent}
          className={cn(
            'p-2 rounded-md transition-colors',
            hasContent && !disabled
              ? 'bg-primary text-primary-foreground hover:bg-primary/90'
              : 'bg-muted text-muted-foreground cursor-not-allowed',
          )}
          title={t('send')}
          aria-label={t('send')}
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};

export default React.memo(DesktopInstructionInput);
