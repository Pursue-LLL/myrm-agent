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

interface DeviceInstructionInputProps {
  selectedRefId: string | null;
  selectedInfo: BrowserRefInfo | null;
  instructionText: string;
  onInstructionChange: (text: string) => void;
  onSubmit: (instruction: string, refId: string | null) => void;
  onClearSelection: () => void;
  disabled?: boolean;
}

const DeviceInstructionInput: React.FC<DeviceInstructionInputProps> = ({
  selectedRefId,
  selectedInfo,
  instructionText,
  onInstructionChange,
  onSubmit,
  onClearSelection,
  disabled,
}) => {
  const t = useTranslations('chat.deviceInspector');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (selectedRefId && inputRef.current) {
      inputRef.current.focus();
    }
  }, [selectedRefId]);

  const handleSubmit = useCallback(() => {
    const text = instructionText.trim();
    if (!text && !selectedRefId) return;
    onSubmit(text, selectedRefId);
  }, [instructionText, selectedRefId, onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const placeholder = selectedRefId ? t('instructionWithElement') : t('instructionPlaceholder');

  return (
    <div className="p-3 border-t border-border bg-background flex flex-col gap-2">
      {selectedRefId && selectedInfo && (
        <SelectedElementBadge refId={selectedRefId} info={selectedInfo} onClear={onClearSelection} />
      )}
      <div className="flex items-end gap-2">
        <textarea
          ref={inputRef}
          value={instructionText}
          onChange={(e) => onInstructionChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={2}
          className={cn(
            'flex-1 resize-none px-3 py-2 text-xs rounded-md border border-input bg-background',
            'focus:outline-none focus:ring-1 focus:ring-ring focus:border-input',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            'placeholder:text-muted-foreground',
          )}
        />
        <button
          type="button"
          onClick={handleSubmit}
          disabled={disabled || (!instructionText.trim() && !selectedRefId)}
          className={cn(
            'p-2 rounded-md transition-colors',
            'bg-primary text-primary-foreground hover:bg-primary/90',
            'disabled:opacity-50 disabled:cursor-not-allowed',
          )}
          title={t('send')}
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};

export default DeviceInstructionInput;
