/**
 * [INPUT] @/store/memory (POS: 记忆 store), @/services/memory::{updateMemory, updateMemoryStatus, restoreMemory} (POS: 记忆接口), @/store/useChatStore + useRetrievalStore (POS: 会话输入 / 向量库孤儿检测), ./memoryNotices (POS: 失败提示)
 * [OUTPUT] useMemoryActions / MemoryActions: 单条记忆的删除（可撤销）、启停、保护、转入对话，以及清空全部记忆的确认状态与动作
 * [POS] 记忆面板的记忆操作层：软删除记忆给出撤销入口；清空全部成功后重新检查向量库孤儿集合，让过期的迁移提醒消失。
 */

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import { restoreMemory as apiRestoreMemory, updateMemory, updateMemoryStatus } from '@/services/memory';
import { useMemoryStore, type Memory, type MemoryType } from '@/store/memory';
import useChatStore from '@/store/useChatStore';
import useRetrievalStore from '@/store/useRetrievalStore';
import { toastFailure } from './memoryNotices';

export function useMemoryActions() {
  const t = useTranslations('memory');
  const router = useRouter();
  const fetchMemories = useMemoryStore((state) => state.fetchMemories);
  const deleteMemory = useMemoryStore((state) => state.deleteMemory);
  const deleteAllMemories = useMemoryStore((state) => state.deleteAllMemories);
  const checkOrphanCollections = useRetrievalStore((state) => state.checkOrphanCollections);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [isClearing, setIsClearing] = useState(false);

  const handleDelete = useCallback(
    async (id: string, memoryType: MemoryType, permanent = false) => {
      const isSoftDeletable = !permanent && (memoryType === 'semantic' || memoryType === 'episodic');
      try {
        await deleteMemory(id, memoryType, permanent);
        if (permanent) {
          toast({ title: t('deleteSuccess'), description: t('trash.purgeSuccess') });
        } else if (isSoftDeletable) {
          toast({
            title: t('deleteSuccess'),
            description: t('trash.undoHint'),
            action: {
              label: t('trash.undo'),
              onClick: async () => {
                try {
                  await apiRestoreMemory(id);
                  await fetchMemories();
                  toast({ title: t('trash.restoreSuccess') });
                } catch {
                  toast({ title: t('trash.restoreFailed'), variant: 'destructive' });
                }
              },
            },
          });
        } else {
          toast({ title: t('deleteSuccess'), description: t('deleteSuccessDesc') });
        }
      } catch (error) {
        toastFailure(t, t('deleteFailed'), error);
      }
    },
    [deleteMemory, fetchMemories, t],
  );

  const handleToggleDisable = useCallback(
    async (memory: Memory) => {
      const newStatus = memory.status === 'disabled' ? 'active' : 'disabled';
      try {
        await updateMemoryStatus(memory.id, newStatus);
        await fetchMemories();
        toast({
          title: newStatus === 'disabled' ? t('disableSuccess') : t('enableSuccess'),
          description: newStatus === 'disabled' ? t('disableSuccessDesc') : t('enableSuccessDesc'),
        });
      } catch (error) {
        toastFailure(t, t('statusUpdateFailed'), error);
      }
    },
    [fetchMemories, t],
  );

  const handleToggleProtect = useCallback(
    async (memory: Memory, nextLocked: boolean) => {
      try {
        await updateMemory(memory.memory_type, memory.id, { is_user_locked: nextLocked });
        await fetchMemories();
        toast({
          title: nextLocked ? t('protectRuleSuccess') : t('releaseProtectionSuccess'),
          description: nextLocked ? t('protectRuleSuccessDesc') : t('releaseProtectionSuccessDesc'),
        });
      } catch (error) {
        toastFailure(t, t('statusUpdateFailed'), error);
      }
    },
    [fetchMemories, t],
  );

  const handleChatFromMemory = useCallback(
    (memory: Memory) => {
      useChatStore.getState().setInputMessage(memory.content);
      router.push('/');
    },
    [router],
  );

  const handleClearAll = useCallback(async () => {
    setIsClearing(true);
    try {
      await deleteAllMemories();
      // Clearing also removes the memories an embedding switch left behind, so the migration reminder above is stale.
      void checkOrphanCollections();
      toast({ title: t('clearAllSuccess'), description: t('clearAllSuccessDesc') });
      setShowClearConfirm(false);
    } catch (error) {
      toastFailure(t, t('clearAllFailed'), error);
    } finally {
      setIsClearing(false);
    }
  }, [deleteAllMemories, checkOrphanCollections, t]);

  return {
    handleDelete,
    handleToggleDisable,
    handleToggleProtect,
    handleChatFromMemory,
    showClearConfirm,
    setShowClearConfirm,
    isClearing,
    handleClearAll,
  };
}

export type MemoryActions = ReturnType<typeof useMemoryActions>;
