/**
 * 快捷指令 Hook：统一 `/` 命令面板。
 *
 * [INPUT]
 * - @/store/useChatStore (POS: Active chat state manager)
 * - @/store/useCommandStore (POS: 系统行为与用户命令注册表)
 * - @/store/skill (POS: 技能市场/本地技能目录)
 * - @/store/useFeatureGateStore (POS: 功能开关)
 *
 * [OUTPUT]
 * - useSlashCommand: 命令面板状态、键盘导航、命令执行（skill 激活 + 模板替换 + 前缀保留）
 *
 * [POS]
 * 聊天输入框 `/` 快捷指令面板。合并系统行为、用户命令、Agent 绑定技能与命令捆绑为统一面板。
 */

import { useState, useMemo, useCallback, useEffect } from 'react';
import { useShallow } from 'zustand/react/shallow';
import useChatStore from '@/store/useChatStore';
import { useCommandStore } from '@/store/useCommandStore';
import { useSkillStore } from '@/store/skill';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import type { SlashItem, SlashAction } from '@/types/command';

/**
 * 斜杠命令后缀（`/命令名`，锚定到光标前文本末尾）。
 *
 * 命令名 token 与技能/命令命名规则一致（技能名允许连字符，见 harness
 * `agent/skills/market/sanitizer.py` 的 `SKILL_NAME_PATTERN`），因此使用
 * `[a-zA-Z0-9_-]`（含 `-`）而非 `\w`（不含 `-`）。面板检测、命令移除、
 * Esc 关闭共用此单一正则，保持三处语义一致。
 */
const SLASH_COMMAND_SUFFIX_RE = /\/[a-zA-Z0-9_-]*$/;

export const useSlashCommand = (inputValue: string, cursorPosition: number) => {
  const { setInputMessage, setPendingExplicitSkillActivation, agentConfig } = useChatStore(
    useShallow((state) => ({
      setInputMessage: state.setInputMessage,
      setPendingExplicitSkillActivation: state.setPendingExplicitSkillActivation,
      agentConfig: state.agentConfig,
    })),
  );
  const { getAllItems, searchItems, recordUsage } = useCommandStore();
  const isCompanionEnabled = useFeatureGateStore((s) => s.isEnabled('companion_mode'));
  const { marketSkills, localSkills, fetchMarketSkills, fetchLocalSkills } = useSkillStore(
    useShallow((state) => ({
      marketSkills: state.marketSkills,
      localSkills: state.localSkills,
      fetchMarketSkills: state.fetchMarketSkills,
      fetchLocalSkills: state.fetchLocalSkills,
    })),
  );

  const [selectedIndex, setSelectedIndex] = useState(0);

  useEffect(() => {
    if (!agentConfig?.selectedSkillIds?.length) {
      return;
    }
    void fetchMarketSkills();
    void fetchLocalSkills();
  }, [agentConfig?.selectedSkillIds, fetchMarketSkills, fetchLocalSkills]);

  const skillActions = useMemo((): SlashAction[] => {
    if (!agentConfig?.selectedSkillIds?.length) {
      return [];
    }
    const allSkills = [...marketSkills, ...localSkills];
    const boundSkills: Array<{ id: string; name: string; description: string; user_invocable: boolean }> =
      agentConfig.selectedSkillIds.flatMap(
        (id): Array<{ id: string; name: string; description: string; user_invocable: boolean }> => {
          const fromCatalog = allSkills.find((skill) => skill.id === id);
          if (fromCatalog) {
            return fromCatalog.user_invocable === false
              ? []
              : [
                  {
                    id: fromCatalog.id,
                    name: fromCatalog.name,
                    description: fromCatalog.description,
                    user_invocable: true,
                  },
                ];
          }
          return [{ id, name: id, description: id, user_invocable: true }];
        },
      );

    const singleSkillActions: SlashAction[] = boundSkills.map((skill): SlashAction => ({
      id: `skill:${skill.id}`,
      name: skill.name.replace(/_skill$/, ''),
      description: skill.description,
      icon: 'zap',
      type: 'action',
      execute: async (_input: string) => ({
        success: true,
        skillActivation: { skillNames: [skill.name] },
      }),
    }));

    const bundleActions: SlashAction[] = [];
    const bindings = agentConfig.commandBindings ?? [];
    for (const binding of bindings) {
      const ids = binding.skill_ids ?? [];
      if (ids.length <= 1) {
        continue;
      }
      const names = ids.map((id: string) => allSkills.find((s) => s.id === id)?.name || id).filter(Boolean);
      if (!names.length) {
        continue;
      }
      const instrPart = binding.instruction ? binding.instruction : undefined;
      bundleActions.push({
        id: `bundle:${binding.command_name}`,
        name: binding.command_name,
        description: binding.description || names.join(' + '),
        icon: 'package',
        type: 'action',
        execute: async (_input: string) => ({
          success: true,
          skillActivation: {
            skillNames: names,
            instruction: instrPart ?? null,
          },
        }),
      });
    }

    return [...singleSkillActions, ...bundleActions];
  }, [agentConfig?.selectedSkillIds, agentConfig?.commandBindings, marketSkills, localSkills]);

  // 检测是否应该显示命令面板
  const { shouldShow, query } = useMemo(() => {
    const textBeforeCursor = inputValue.slice(0, cursorPosition);
    const match = textBeforeCursor.match(SLASH_COMMAND_SUFFIX_RE);

    if (!match) {
      return { shouldShow: false, query: '' };
    }

    return {
      shouldShow: true,
      // match[0] 形如 "/report"（含斜杠），query 只取命令名部分
      query: match[0].slice(1),
    };
  }, [inputValue, cursorPosition]);

  // 过滤后的命令列表（合并系统命令 + 技能快捷触发）
  const filteredItems = useMemo(() => {
    if (!shouldShow) {
      return [];
    }

    const baseItems = !query ? getAllItems() : searchItems(query);

    const lowerQuery = query.toLowerCase();
    const matchingSkills = !query
      ? skillActions
      : skillActions.filter(
          (s) => s.name.toLowerCase().includes(lowerQuery) || s.description.toLowerCase().includes(lowerQuery),
        );

    return [...baseItems, ...matchingSkills].filter((item) => item.id !== 'builtin:pet' || isCompanionEnabled);
  }, [shouldShow, query, getAllItems, searchItems, skillActions, isCompanionEnabled]);

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
          if (result.skillActivation) {
            setPendingExplicitSkillActivation(result.skillActivation);
            // 只移除末尾 /命令 部分，保留前后文本作为指令，避免清空用户已输入的指令前缀
            const textBeforeCursor = inputValue.slice(0, cursorPosition);
            const textAfterCursor = inputValue.slice(cursorPosition);
            const beforeCommand = textBeforeCursor.replace(SLASH_COMMAND_SUFFIX_RE, '');
            setInputMessage(beforeCommand + textAfterCursor);
          } else if (result.newInputValue !== undefined) {
            setInputMessage(result.newInputValue);
          }
        } else {
          // 获取命令前后的文本
          const textBeforeCursor = inputValue.slice(0, cursorPosition);
          const textAfterCursor = inputValue.slice(cursorPosition);

          // 移除末尾 /命令 部分，保留之前的文本
          const beforeCommand = textBeforeCursor.replace(SLASH_COMMAND_SUFFIX_RE, '');

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
    [inputValue, cursorPosition, setInputMessage, setPendingExplicitSkillActivation, recordUsage],
  );

  // 键盘导航
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!shouldShow || filteredItems.length === 0) {
        return;
      }

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex((prev) => (prev + 1) % filteredItems.length);
          break;

        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex((prev) => (prev === 0 ? filteredItems.length - 1 : prev - 1));
          break;

        case 'Tab':
        case 'Enter':
          if (shouldShow && filteredItems.length > 0) {
            e.preventDefault();
            executeCommand(filteredItems[selectedIndex]);
          }
          break;

        case 'Escape':
          e.preventDefault();
          // 关闭面板（通过删除斜杠命令）
          const textBeforeCursor = inputValue.slice(0, cursorPosition);
          const textAfterCursor = inputValue.slice(cursorPosition);

          const beforeSlash = textBeforeCursor.replace(SLASH_COMMAND_SUFFIX_RE, '');
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
