/**
 * [INPUT]
 * - @/services/statistics::updateTimelineMemory, deleteTimelineMemory, archiveTimelineSkill (POS: 学习时间线治理接口)
 * - @/services/memory::restoreMemory (POS: 记忆回收站恢复，用于撤销删除)
 * - ./learningTimelineMeta (POS: 节点状态读取与排序)
 *
 * [OUTPUT]
 * - useTimelineGovernance: 时间线行内治理动作（保存编辑 / 删除记忆 / 归档或恢复技能），
 *   统一提供乐观更新、失败回滚与撤销提示
 *
 * [POS]
 * 学习时间线治理逻辑。只改写调用方传入的列表状态，不持有列表本身。
 */

import { useCallback, type Dispatch, type SetStateAction } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { showApiError } from '@/lib/api';
import { restoreMemory } from '@/services/memory';
import {
  archiveTimelineSkill,
  deleteTimelineMemory,
  updateTimelineMemory,
  type LearningTimelineItem,
} from '@/services/statistics';
import type { TimelineEditDraft } from './TimelineNodeCard';
import {
  RECOVERABLE_MEMORY_TYPES,
  compareTimelineItems,
  memoryTypeOf,
  skillNameOf,
  toImportanceScale,
} from './learningTimelineMeta';

const UNDO_TOAST_MS = 8000;

const insertSorted = (items: LearningTimelineItem[], item: LearningTimelineItem): LearningTimelineItem[] =>
  items.some((it) => it.id === item.id) ? items : [...items, item].sort(compareTimelineItems);

interface TimelineListSetters {
  setItems: Dispatch<SetStateAction<LearningTimelineItem[]>>;
  setTotalCount: Dispatch<SetStateAction<number>>;
}

export function useTimelineGovernance({ setItems, setTotalCount }: TimelineListSetters) {
  const t = useTranslations('growthDashboard.learningTimeline');

  const removeItem = useCallback(
    (item: LearningTimelineItem) => {
      setItems((prev) => prev.filter((it) => it.id !== item.id));
      setTotalCount((prev) => Math.max(0, prev - 1));
    },
    [setItems, setTotalCount],
  );

  const reinsertItem = useCallback(
    (item: LearningTimelineItem) => {
      setItems((prev) => insertSorted(prev, item));
      setTotalCount((prev) => prev + 1);
    },
    [setItems, setTotalCount],
  );

  const patchItem = useCallback(
    (id: string, patch: (it: LearningTimelineItem) => LearningTimelineItem) => {
      setItems((prev) => prev.map((it) => (it.id === id ? patch(it) : it)));
    },
    [setItems],
  );

  const saveEdit = useCallback(
    async (item: LearningTimelineItem, draft: TimelineEditDraft): Promise<boolean> => {
      const isProcedural = item.kind === 'procedural_memory';
      // Importance is only submitted when the user moved the slider: the 1-10 scale is coarser than the stored
      // value, so echoing it back would silently rewrite (and possibly protect) a memory on a content-only edit.
      const importanceChanged = !isProcedural && draft.importance !== toImportanceScale(item.importance);
      const importance = importanceChanged ? draft.importance / 10 : undefined;
      const reasoning = isProcedural ? draft.reasoning.trim() : '';
      try {
        await updateTimelineMemory(memoryTypeOf(item), item.id, {
          content: draft.content,
          importance,
          reasoning: reasoning || undefined,
        });
      } catch (err) {
        showApiError(err);
        return false;
      }
      patchItem(item.id, (it) => ({
        ...it,
        content: draft.content,
        importance: importance ?? it.importance,
        // The server protects every edited memory (procedural lock, semantic/episodic pin).
        is_user_protected: true,
        metadata: reasoning ? { ...it.metadata, reasoning } : it.metadata,
      }));
      toast.success(t('toast.updateSuccess'));
      return true;
    },
    [patchItem, t],
  );

  const setSkillArchived = useCallback(
    async (item: LearningTimelineItem, archived: boolean): Promise<boolean> => {
      patchItem(item.id, (it) => ({ ...it, metadata: { ...it.metadata, archived } }));
      try {
        await archiveTimelineSkill(skillNameOf(item), !archived);
        return true;
      } catch (err) {
        patchItem(item.id, (it) => ({ ...it, metadata: { ...it.metadata, archived: !archived } }));
        showApiError(err);
        return false;
      }
    },
    [patchItem],
  );

  const archiveSkill = useCallback(
    async (item: LearningTimelineItem, archived: boolean) => {
      if (!(await setSkillArchived(item, archived))) {
        return;
      }
      toast.success(t(archived ? 'toast.archiveSuccess' : 'toast.unarchiveSuccess'), {
        duration: UNDO_TOAST_MS,
        action: {
          label: t('toast.undo'),
          onClick: () => {
            void setSkillArchived(item, !archived).then((ok) => {
              if (!ok) {
                toast.error(t('toast.undoFailed'));
              }
            });
          },
        },
      });
    },
    [setSkillArchived, t],
  );

  const deleteMemory = useCallback(
    async (item: LearningTimelineItem) => {
      const memoryType = memoryTypeOf(item);
      removeItem(item);
      try {
        await deleteTimelineMemory(item.id, memoryType);
      } catch (err) {
        reinsertItem(item);
        showApiError(err);
        return;
      }
      if (!RECOVERABLE_MEMORY_TYPES.has(memoryType)) {
        toast.success(t('toast.deletePermanentSuccess'));
        return;
      }
      toast.success(t('toast.deleteSuccess'), {
        duration: UNDO_TOAST_MS,
        action: {
          label: t('toast.undo'),
          onClick: () => {
            restoreMemory(item.id)
              .then(() => reinsertItem(item))
              .catch(() => toast.error(t('toast.undoFailed')));
          },
        },
      });
    },
    [reinsertItem, removeItem, t],
  );

  return { saveEdit, archiveSkill, deleteMemory };
}
