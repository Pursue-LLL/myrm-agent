/**
 * 快捷指令Hook
 *
 * Merges system actions, user commands, and agent-bound skills into a unified / command palette.
 */

import { useState, useMemo, useCallback, useEffect } from 'react';
import { useShallow } from 'zustand/react/shallow';
import useChatStore from '@/store/useChatStore';
import { useCommandStore } from '@/store/useCommandStore';
import { useSkillStore } from '@/store/skill';
import type { SlashItem, SlashAction } from '@/types/command';

export const useSlashCommand = (inputValue: string, cursorPosition: number) => {
  const { setInputMessage, agentConfig } = useChatStore(
    useShallow((state) => ({
      setInputMessage: state.setInputMessage,
      agentConfig: state.agentConfig,
    })),
  );
  const { getAllItems, searchItems, recordUsage } = useCommandStore();
  const { marketSkills, localSkills } = useSkillStore(
    useShallow((state) => ({
      marketSkills: state.marketSkills,
      localSkills: state.localSkills,
    })),
  );

  const [selectedIndex, setSelectedIndex] = useState(0);

  const skillActions = useMemo((): SlashAction[] => {
    if (!agentConfig?.selectedSkillIds?.length) return [];
    const allSkills = [...marketSkills, ...localSkills];
    const boundSkills = agentConfig.selectedSkillIds
      .map((id) => allSkills.find((s) => s.id === id))
      .filter((s): s is (typeof allSkills)[number] => s != null && s.user_invocable !== false);

    return boundSkills.map(
      (skill): SlashAction => ({
        id: `skill:${skill.id}`,
        name: skill.name.replace(/_skill$/, ''),
        description: skill.description,
        icon: '⚡',
        type: 'action',
        execute: async (_input: string) => ({
          success: true,
          newInputValue: `[use ${skill.name}] `,
        }),
      }),
    );
  }, [agentConfig?.selectedSkillIds, marketSkills, localSkills]);

  // 检测是否应该显示命令面板
  const { shouldShow, query } = useMemo(() => {
    const textBeforeCursor = inputValue.slice(0, cursorPosition);
    const match = textBeforeCursor.match(/\/([a-zA-Z0-9_-]*)$/);

    if (!match) {
      return { shouldShow: false, query: '' };
    }

    return {
      shouldShow: true,
      query: match[1],
    };
  }, [inputValue, cursorPosition]);

  // 过滤后的命令列表（合并系统命令 + 技能快捷触发）
  const filteredItems = useMemo(() => {
    if (!shouldShow) return [];

    const baseItems = !query ? getAllItems() : searchItems(query);

    const matchingSkills = !query
      ? skillActions
      : skillActions.filter((s) => s.name.toLowerCase().includes(query.toLowerCase()));

    return [...baseItems, ...matchingSkills];
  }, [shouldShow, query, getAllItems, searchItems, skillActions]);

  // 执行命令
  const executeCommand = useCallback(
    async (item: SlashItem) => {
      try {
        if (item.type === 'action') {
          // 执行系统行为
          const result = await item.execute(inputValue);

          // 处理执行结果
          if (!result.success && result.error) {
            console.error('[SlashCommand] Action failed:', result.error);
          }

          // 如果行为返回了新的输入值，更新输入框
          if (result.newInputValue !== undefined) {
            setInputMessage(result.newInputValue);
          }
        } else {
          // 获取命令前后的文本
          const textBeforeCursor = inputValue.slice(0, cursorPosition);
          const textAfterCursor = inputValue.slice(cursorPosition);

          // 移除 /命令 部分，保留之前的文本
          const match = textBeforeCursor.match(/^(.*)\/\w*$/);
          const beforeCommand = match ? match[1] : '';

          // 构建新的输入值：直接在光标位置追加指令文本
          const newValue = beforeCommand + item.template + textAfterCursor;

          setInputMessage(newValue);

          // 记录使用
          recordUsage(item.id);
        }
      } catch (error) {
        console.error('[SlashCommand] Execute failed:', error);
      }

      // 重置选中索引（命令执行后关闭面板）
      setSelectedIndex(0);
    },
    [inputValue, cursorPosition, setInputMessage, recordUsage],
  );

  // 键盘导航
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!shouldShow || filteredItems.length === 0) return;

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex((prev) => (prev + 1) % filteredItems.length);
          break;

        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex((prev) => (prev === 0 ? filteredItems.length - 1 : prev - 1));
          break;

        case 'Enter':
          if (shouldShow && filteredItems.length > 0) {
            e.preventDefault();
            executeCommand(filteredItems[selectedIndex]);
          }
          break;

        case 'Escape':
          e.preventDefault();
          // 关闭面板（通过删除斜杠字符）
          const textBeforeCursor = inputValue.slice(0, cursorPosition);
          const textAfterCursor = inputValue.slice(cursorPosition);

          const beforeSlash = textBeforeCursor.replace(/\/\w*$/, '');
          setInputMessage(beforeSlash + textAfterCursor);
          break;
      }
    },
    [shouldShow, filteredItems, selectedIndex, executeCommand, inputValue, cursorPosition, setInputMessage],
  );

  // 当过滤结果变化时，重置选中索引
  useEffect(() => {
    setSelectedIndex(0);
  }, [filteredItems.length]);

  return {
    showCommandPalette: shouldShow,
    commandQuery: query,
    filteredItems,
    selectedIndex,
    setSelectedIndex,
    executeCommand,
    handleKeyDown,
  };
};
