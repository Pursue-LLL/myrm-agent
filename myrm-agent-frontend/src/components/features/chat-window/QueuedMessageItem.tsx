/**
 * [INPUT]
 * - @/store/chat/useMessageQueueStore::QueuedMessage (POS: 排队消息内存状态源)
 * - @/lib/utils/imeUtils::isImeComposing (POS: IME 输入法兼容性守卫)
 *
 * [OUTPUT]
 * - QueuedMessageItem: 单条排队消息（可拖拽排序、就地编辑、移出队列）。
 *
 * [POS]
 * 排队消息列表的行组件。编辑态使用多行输入并拦截按键冒泡，避免回车被外层输入表单当作"发送当前输入"。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import TextareaAutosize from 'react-textarea-autosize';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Check, ClockCountdown, DotsSixVertical, Paperclip, PencilSimple, X } from '@phosphor-icons/react';
import { isImeComposing } from '@/lib/utils/imeUtils';
import type { QueuedMessage } from '@/store/chat/useMessageQueueStore';

interface QueuedMessageItemProps {
  message: QueuedMessage;
  index: number;
  total: number;
  isEditing: boolean;
  onStartEdit: (id: string) => void;
  onSaveEdit: (id: string, text: string) => void;
  onCancelEdit: () => void;
  onRemove: (id: string) => void;
}

const ICON_BUTTON_CLASS =
  'inline-flex items-center justify-center rounded-md p-1.5 transition-colors pointer-coarse:p-2.5';

function QueuedMessageEditor({
  message,
  onSave,
  onCancel,
}: {
  message: QueuedMessage;
  onSave: (text: string) => void;
  onCancel: () => void;
}) {
  const t = useTranslations('chat');
  const [draft, setDraft] = useState(message.text);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  // A files-only message has no text to lose; an empty message without files could never be sent.
  const canSave = draft.trim().length > 0 || message.files.length > 0;

  useEffect(() => {
    const input = inputRef.current;
    if (input) {
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
    }
  }, []);

  const save = useCallback(() => {
    if (canSave) {
      onSave(draft.trim());
    }
  }, [canSave, draft, onSave]);

  return (
    <div className="flex min-w-0 flex-1 items-start gap-2">
      <ClockCountdown size={14} className="mt-1.5 shrink-0 text-accent-warm" aria-hidden />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <TextareaAutosize
          ref={inputRef}
          value={draft}
          minRows={1}
          maxRows={8}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            // The list lives inside the composer form, whose key handler would send the composer text on Enter.
            event.stopPropagation();
            if (isImeComposing(event)) {
              return;
            }
            if (event.key === 'Escape') {
              event.preventDefault();
              onCancel();
            } else if (event.key === 'Enter' && !event.shiftKey && !event.altKey) {
              event.preventDefault();
              save();
            }
          }}
          aria-label={t('queue.edit')}
          className="w-full resize-none border-b border-accent-warm/50 bg-transparent py-0.5 text-sm text-foreground outline-none focus:border-accent-warm"
        />
        <span className="text-[11px] text-muted-foreground">{t('queue.editHint')}</span>
      </div>
      <button
        type="button"
        onClick={save}
        disabled={!canSave}
        className={`${ICON_BUTTON_CLASS} text-accent-warm hover:bg-accent-warm/10 disabled:opacity-40`}
        aria-label={t('queue.saveEdit')}
        title={t('queue.saveEdit')}
      >
        <Check size={14} />
      </button>
      <button
        type="button"
        onClick={onCancel}
        className={`${ICON_BUTTON_CLASS} text-muted-foreground hover:bg-muted hover:text-foreground`}
        aria-label={t('queue.cancelEdit')}
        title={t('queue.cancelEdit')}
      >
        <X size={14} />
      </button>
    </div>
  );
}

export function QueuedMessageItem({
  message,
  index,
  total,
  isEditing,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onRemove,
}: QueuedMessageItemProps) {
  const t = useTranslations('chat');
  const tTurn = useTranslations('chat.turnCapabilities');
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: message.id,
    disabled: isEditing,
  });

  const overrideSummary = useMemo(() => {
    const selection = message.turnCapabilitySelection;
    if (!selection) {
      return null;
    }
    const parts: string[] = [];
    if (selection.skillIds !== null) {
      parts.push(tTurn('overrideSkillsShort', { skills: selection.skillIds.length }));
    }
    if (selection.mcpNames !== null) {
      parts.push(tTurn('overrideMcpShort', { mcps: selection.mcpNames.length }));
    }
    return parts.join(' · ');
  }, [message.turnCapabilitySelection, tTurn]);

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 10 : undefined,
  };

  return (
    <li
      ref={setNodeRef}
      style={style}
      className="group/queue flex items-start justify-between gap-2 rounded-lg border border-accent-warm/25 bg-primary/8 px-3 py-2 text-sm shadow-brand"
    >
      {isEditing ? (
        <QueuedMessageEditor
          message={message}
          onSave={(text) => onSaveEdit(message.id, text)}
          onCancel={onCancelEdit}
        />
      ) : (
        <>
          <div className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden">
            <button
              type="button"
              {...attributes}
              {...listeners}
              aria-label={t('queue.reorder')}
              className={`${ICON_BUTTON_CLASS} -ml-1.5 shrink-0 cursor-grab touch-none text-muted-foreground/60 hover:text-foreground active:cursor-grabbing`}
            >
              <DotsSixVertical size={14} weight="bold" />
            </button>
            <ClockCountdown size={14} className="shrink-0 animate-pulse text-accent-warm" aria-hidden />
            <span className="shrink-0 font-medium text-accent-warm">
              {t('queue.queued', { index: String(index + 1), total: String(total) })}
            </span>
            {overrideSummary && (
              <span
                className="inline-flex shrink-0 items-center rounded border border-primary/25 bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary"
                title={overrideSummary}
              >
                {overrideSummary}
              </span>
            )}
            {message.files.length > 0 && (
              <span className="inline-flex shrink-0 items-center gap-1 rounded border border-border bg-muted/60 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                <Paperclip size={11} aria-hidden />
                {t('queue.attachments', { count: message.files.length })}
              </span>
            )}
            {/* oxlint-disable-next-line jsx-a11y/no-static-element-interactions -- pointer shortcut; keyboard users reach the same action through the Edit button */}
            <span
              className="truncate text-muted-foreground"
              title={message.text}
              onDoubleClick={() => onStartEdit(message.id)}
            >
              {message.text}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-0.5 transition-opacity [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-focus-within/queue:opacity-100 [@media(hover:hover)]:group-hover/queue:opacity-100">
            <button
              type="button"
              onClick={() => onStartEdit(message.id)}
              className={`${ICON_BUTTON_CLASS} text-muted-foreground hover:bg-muted hover:text-foreground`}
              aria-label={t('queue.edit')}
              title={t('queue.edit')}
            >
              <PencilSimple size={14} />
            </button>
            <button
              type="button"
              onClick={() => onRemove(message.id)}
              className={`${ICON_BUTTON_CLASS} text-muted-foreground hover:bg-destructive/10 hover:text-destructive`}
              aria-label={t('queue.cancel')}
              title={t('queue.cancel')}
            >
              <X size={14} />
            </button>
          </div>
        </>
      )}
    </li>
  );
}
