'use client';

/**
 * [INPUT]
 * - @dnd-kit/core、@dnd-kit/sortable (POS: 置顶会话的拖拽排序)
 * - @/hooks/ui/useDndAccessibility::useDndAccessibility (POS: 键盘拖拽的说明与播报，念会话标题)
 * - @/store/useChatStore::useChatStore (POS: 置顶顺序的持久化入口)
 * - ./ChatHistoryRow (POS: 会话条目与可拖拽的置顶条目)
 * - ./dateGroupUtils::DateGroup (POS: 按日期分好的一组会话)
 *
 * [OUTPUT]
 * - PinnedSection: 置顶会话区，带序号，可拖拽排序。
 * - DateGroupSection: 一个可折叠的日期分组。
 * - HistoryRowProps: 列表传给每一行的公共属性。
 *
 * [POS]
 * 会话列表里的两种分区。置顶区自己持有拖拽的传感器、无障碍播报与排序提交，只在有置顶会话时挂载；
 * 日期分组的折叠状态由调用方保存，折叠时行高收到 0 而不卸载，展开收起带过渡。
 */
import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  type UniqueIdentifier,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import { arrayMove, SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { ChevronDown, Pin } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useCallback } from 'react';
import { useDndAccessibility } from '@/hooks/ui/useDndAccessibility';
import { cn } from '@/lib/utils/classnameUtils';
import type { ChatItem } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { ChatHistoryRow, type ChatHistoryRowProps, SortablePinnedRow } from './ChatHistoryRow';
import type { DateGroup } from './dateGroupUtils';

/** What every row gets from the list, apart from the per-section selection and numbering. */
export type HistoryRowProps = Omit<ChatHistoryRowProps, 'pinIndex' | 'batchMode' | 'isSelected' | 'onToggleSelect'>;

interface PinnedSectionProps {
  chats: ChatItem[];
  isMobile: boolean;
  rowProps: (chat: ChatItem) => HistoryRowProps;
}

export function PinnedSection({ chats, isMobile, rowProps }: PinnedSectionProps) {
  const t = useTranslations();
  const reorderPinnedChats = useChatStore((s) => s.reorderPinnedChats);

  const dndSensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  );
  const chatTitle = useCallback((id: UniqueIdentifier) => chats.find((chat) => chat.id === id)?.title, [chats]);
  const dndAccessibility = useDndAccessibility(chatTitle);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) {
        return;
      }
      const oldIdx = chats.findIndex((c) => c.id === active.id);
      const newIdx = chats.findIndex((c) => c.id === over.id);
      if (oldIdx === -1 || newIdx === -1) {
        return;
      }
      const reordered = arrayMove(chats, oldIdx, newIdx);
      reorderPinnedChats(reordered.map((c) => c.id));
    },
    [chats, reorderPinnedChats],
  );

  return (
    <>
      <div className="flex items-center gap-1.5 px-2 py-1">
        <Pin size={10} className="text-primary/60" />
        <span
          className={cn('text-[10px] font-medium text-primary/60 uppercase tracking-wider', isMobile && 'text-[9px]')}
        >
          {t('chat.pin.section')}
        </span>
      </div>
      <DndContext
        sensors={dndSensors}
        accessibility={dndAccessibility}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext items={chats.map((c) => c.id)} strategy={verticalListSortingStrategy}>
          {chats.map((chat, idx) => (
            <SortablePinnedRow key={chat.id} pinIndex={idx + 1} {...rowProps(chat)} />
          ))}
        </SortableContext>
      </DndContext>
      <div className="mx-2 my-1 border-t border-black/5 dark:border-white/5" />
    </>
  );
}

interface DateGroupSectionProps {
  group: DateGroup;
  collapsed: boolean;
  onToggle: (key: DateGroup['key']) => void;
  isMobile: boolean;
  batchMode: boolean;
  selectedIds: ReadonlySet<string>;
  onToggleSelect: (id: string) => void;
  rowProps: (chat: ChatItem) => HistoryRowProps;
}

export function DateGroupSection({
  group,
  collapsed,
  onToggle,
  isMobile,
  batchMode,
  selectedIds,
  onToggleSelect,
  rowProps,
}: DateGroupSectionProps) {
  const t = useTranslations();

  return (
    <div>
      <button
        onClick={() => onToggle(group.key)}
        className={cn(
          'flex items-center gap-1.5 w-full px-2 py-1 cursor-pointer select-none',
          'hover:bg-black/3 dark:hover:bg-white/3 rounded transition-colors',
        )}
      >
        <ChevronDown
          size={10}
          className={cn(
            'text-black/40 dark:text-white/40 flex-shrink-0 transition-transform duration-200',
            collapsed && '-rotate-90',
          )}
        />
        <span
          className={cn(
            'text-[10px] font-medium text-black/50 dark:text-white/50 uppercase tracking-wider',
            isMobile && 'text-[9px]',
          )}
        >
          {t(`chat.dateGroup.${group.key}` as Parameters<typeof t>[0])}
        </span>
      </button>
      <div
        className="grid transition-[grid-template-rows] duration-200 ease-out"
        style={{ gridTemplateRows: collapsed ? '0fr' : '1fr' }}
      >
        <div className="overflow-hidden">
          {group.items.map((chat) => (
            <ChatHistoryRow
              key={chat.id}
              batchMode={batchMode}
              isSelected={selectedIds.has(chat.id)}
              onToggleSelect={onToggleSelect}
              {...rowProps(chat)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
