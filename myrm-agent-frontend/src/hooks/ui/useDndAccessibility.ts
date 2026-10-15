/**
 * [INPUT]
 * - next-intl::useTranslations (POS: common.dnd 本地化文案)
 * - @dnd-kit/core::Announcements, ScreenReaderInstructions, UniqueIdentifier (POS: 拖拽无障碍配置类型)
 *
 * [OUTPUT]
 * - useDndAccessibility: DndContext 的 `accessibility` 属性（本地化的键盘操作说明与实时播报）
 * - useDndItemLabels: 单个拖拽项的本地化文案（`aria-roledescription`、拖拽手柄名称）
 *
 * [POS]
 * 所有 @dnd-kit 拖拽站点共享的屏幕阅读器文案层。dnd-kit 自带的说明与播报只有英文，且播报里直接念内部 id
 * （任务 id、列状态枚举），这里统一换成当前语言和用户看得懂的名称；站点只负责提供「id → 名称」。
 */
import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import type { Announcements, ScreenReaderInstructions, UniqueIdentifier } from '@dnd-kit/core';

interface DndAccessibility {
  announcements: Announcements;
  screenReaderInstructions: ScreenReaderInstructions;
}

/**
 * @param labelOf 把拖拽项 / 放置目标的 id 换成用户可读的名称；认不出的 id 返回 undefined，
 *   播报会用通用称呼，而不是念出 id。应保持引用稳定（`useCallback`），否则每次渲染都会重建配置。
 */
export function useDndAccessibility(labelOf: (id: UniqueIdentifier) => string | undefined): DndAccessibility {
  const t = useTranslations('common.dnd');

  return useMemo(() => {
    const nameOf = (id: UniqueIdentifier) => labelOf(id) ?? t('unknownItem');
    // 放在自己身上（排序列表里回到原位）不算放到某个目标上。
    const targetOf = (active: UniqueIdentifier, over: { id: UniqueIdentifier } | null) =>
      over && over.id !== active ? over.id : null;
    // dnd-kit 在拾起的同一批更新里就会派发「悬停在起点」事件，播报文本会被它立刻顶掉，
    // 屏幕阅读器永远念不到「已拾起」，所以拾起后的第一次悬停事件不播报。
    let awaitingStartPosition = false;

    const announcements: Announcements = {
      onDragStart: ({ active }) => {
        awaitingStartPosition = true;
        return t('pickedUp', { item: nameOf(active.id) });
      },
      onDragOver: ({ active, over }) => {
        if (awaitingStartPosition) {
          awaitingStartPosition = false;
          return undefined;
        }
        const item = nameOf(active.id);
        if (!over) {
          return t('leftTarget', { item });
        }
        const target = targetOf(active.id, over);
        return target === null ? t('backAtStart', { item }) : t('movedOver', { item, target: nameOf(target) });
      },
      onDragEnd: ({ active, over }) => {
        const item = nameOf(active.id);
        const target = targetOf(active.id, over);
        return target === null ? t('dropped', { item }) : t('droppedOn', { item, target: nameOf(target) });
      },
      onDragCancel: ({ active }) => t('cancelled', { item: nameOf(active.id) }),
    };

    return { announcements, screenReaderInstructions: { draggable: t('instructions') } };
  }, [t, labelOf]);
}

export function useDndItemLabels(): { roleDescription: string; handleLabel: string } {
  const t = useTranslations('common.dnd');
  return useMemo(() => ({ roleDescription: t('roleDescription'), handleLabel: t('handleLabel') }), [t]);
}
