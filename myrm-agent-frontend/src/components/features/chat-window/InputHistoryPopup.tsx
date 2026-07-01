'use client';

/**
 * [INPUT]
 * - InputHistoryPopupState from useInputHistory
 *
 * [OUTPUT]
 * - InputHistoryPopup: 输入框上方的历史条目弹窗。
 *
 * [POS]
 * 输入历史弹窗组件。以列表形式展示历史 prompt，支持键盘高亮和鼠标选择。
 */

import { memo, useEffect, useRef } from 'react';
import type { InputHistoryEntry, InputHistoryPopupState } from '@/hooks/useInputHistory';

const rtf = typeof Intl !== 'undefined' ? new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }) : null;

function formatRelativeTime(timestamp: number): string {
  const diff = Date.now() - timestamp;
  const minutes = Math.floor(diff / 60000);
  if (!rtf) return new Date(timestamp).toLocaleString();
  if (minutes < 1) return rtf.format(0, 'minute');
  if (minutes < 60) return rtf.format(-minutes, 'minute');
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return rtf.format(-hours, 'hour');
  const days = Math.floor(hours / 24);
  if (days < 7) return rtf.format(-days, 'day');
  return new Date(timestamp).toLocaleDateString();
}

function getPreviewText(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

interface InputHistoryPopupProps {
  popup: InputHistoryPopupState;
  onSelect: (index: number) => void;
  onHover: (index: number) => void;
  onClose: () => void;
}

const InputHistoryPopup = memo<InputHistoryPopupProps>(({ popup, onSelect, onHover, onClose }) => {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!popup.open) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (rootRef.current?.contains(event.target as Node)) return;
      onClose();
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [popup.open, onClose]);

  useEffect(() => {
    if (!popup.open) return;
    const node = rootRef.current?.querySelector<HTMLElement>(`[data-history-index="${popup.activeIndex}"]`);
    node?.scrollIntoView({ block: 'nearest' });
  }, [popup.activeIndex, popup.open]);

  if (!popup.open || popup.entries.length === 0) return null;

  return (
    <div
      ref={rootRef}
      role="listbox"
      aria-label="输入历史"
      className="absolute bottom-full left-0 right-0 z-50 mb-2 max-h-60 overflow-y-auto rounded-lg border border-border bg-popover p-1 shadow-lg"
    >
      {popup.entries.map((entry, index) => (
        <div
          key={`${entry.createdAt}-${index}`}
          data-history-index={index}
          role="option"
          aria-selected={index === popup.activeIndex}
          onMouseEnter={() => onHover(index)}
          onMouseDown={(e) => {
            e.preventDefault();
            onSelect(index);
          }}
          className={`cursor-pointer truncate rounded-md px-3 py-1.5 text-sm transition-colors ${
            index === popup.activeIndex
              ? 'bg-accent text-accent-foreground'
              : 'text-muted-foreground hover:bg-muted'
          }`}
          title={`${getPreviewText(entry.text)}\n${formatRelativeTime(entry.createdAt)}`}
        >
          {getPreviewText(entry.text)}
        </div>
      ))}
    </div>
  );
});

InputHistoryPopup.displayName = 'InputHistoryPopup';

export default InputHistoryPopup;
