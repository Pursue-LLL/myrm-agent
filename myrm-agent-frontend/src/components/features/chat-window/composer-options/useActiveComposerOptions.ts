'use client';

/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线，持有各模式开关)
 * - next-intl::useTranslations, useLocale (POS: 文案与语言)
 *
 * [OUTPUT]
 * - useActiveComposerOptions: one localized sentence naming the modes that are on, or null when none is.
 *
 * [POS]
 * The options region can be closed while a mode that changes the next message is on. This is the single place that
 * decides which modes count, mirroring the condition under which each control shows itself as on: deep search only
 * exists beside the fast action mode, a goal only beside the agent mode, so a value left over from the other mode
 * is not announced. A mode that stays on across messages and changes cost, reach or privacy belongs here.
 */

import { useLocale, useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';

import useChatStore from '@/store/useChatStore';

export function useActiveComposerOptions(): string | null {
  const t = useTranslations();
  const locale = useLocale();
  const { deepSearch, workflow, goal, incognito } = useChatStore(
    useShallow((state) => ({
      deepSearch: state.actionMode === 'fast' && state.searchDepth === 'deep',
      workflow: state.isWorkflowMode,
      goal: state.actionMode === 'agent' && state.isGoalMode,
      incognito: state.incognitoMode,
    })),
  );

  const names = [
    deepSearch && t('mode.deepSearchTitle'),
    workflow && t('mode.workflowModeLabel'),
    goal && t('Goal.enableGoalMode'),
    incognito && t('memory.incognitoMode'),
  ].filter((name): name is string => typeof name === 'string');

  if (names.length === 0) {
    return null;
  }
  const list = new Intl.ListFormat(locale, { style: 'narrow', type: 'conjunction' }).format(names);
  return t('chat.input.toolbarActive', { names: list });
}
