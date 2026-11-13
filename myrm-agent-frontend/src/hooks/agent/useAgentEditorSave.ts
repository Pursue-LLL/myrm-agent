'use client';

/**
 * [INPUT]
 * @/hooks/agent/useAgentEditor::useAgentEditor (POS: 表单整体编辑与保存)
 * @/hooks/agent/useAgentCommandBindings::AgentCommandBindingsState (POS: 命令绑定独立持久化)
 * @/services/riskHeldToast::isRiskHeldError (POS: 风险拦截错误判定)
 *
 * [OUTPUT]
 * useAgentEditorSave: 面板级统一的未保存状态、保存与“保存并开始对话”
 *
 * [POS]
 * Agent 编辑面板的保存编排。命令绑定与其余配置走两条互不覆盖的更新请求，对用户只呈现一个保存入口：
 * 绑定先保存，校验未通过或失败即整体中止；只有绑定有改动时不再触发整体保存，避免多余的全量更新与快照，
 * 并由本层给出“已保存”提示（整体保存自带成功提示，不重复）。
 */

import { useCallback } from 'react';
import type { AgentCommandBindingsState } from '@/hooks/agent/useAgentCommandBindings';
import type { useAgentEditor } from '@/hooks/agent/useAgentEditor';
import { toast } from '@/hooks/shared/useToast';
import { isRiskHeldError } from '@/services/riskHeldToast';

type AgentEditor = ReturnType<typeof useAgentEditor>;

export function useAgentEditorSave(
  editor: Pick<AgentEditor, 'hasChanges' | 'saving' | 'isReadonly' | 'handleSave' | 'handleStartChat'>,
  commandBindings: Pick<AgentCommandBindingsState, 'dirty' | 'canSave' | 'saving' | 'save'>,
  t: (key: string) => string,
) {
  const { hasChanges, isReadonly, handleSave: saveEditor, handleStartChat: startChat } = editor;
  const { canSave, save: saveBindingsDraft } = commandBindings;
  // 内置只读智能体不可保存；键盘仍可改动草稿，因此在此统一排除。
  const bindingsDirty = commandBindings.dirty && !isReadonly;

  /** 返回 false 表示应中止后续动作，失败原因已提示给用户。 */
  const saveBindings = useCallback(async (): Promise<boolean> => {
    if (!bindingsDirty) {
      return true;
    }
    if (!canSave) {
      toast({ title: t('agent.commandBindings.fixBeforeSave'), variant: 'destructive' });
      return false;
    }
    try {
      await saveBindingsDraft();
      return true;
    } catch (error) {
      // 被服务端风控拦下时，统一提示已经弹出，这里不再叠加“操作失败”。
      if (!isRiskHeldError(error)) {
        toast({
          title: t('agent.operationFailed'),
          description: error instanceof Error ? error.message : undefined,
          variant: 'destructive',
        });
      }
      return false;
    }
  }, [bindingsDirty, canSave, saveBindingsDraft, t]);

  const handleSave = useCallback(async () => {
    if (!(await saveBindings())) {
      return;
    }
    if (!hasChanges) {
      if (bindingsDirty) {
        toast({ title: t('agent.commandBindings.saved') });
      }
      return;
    }
    try {
      await saveEditor();
    } catch {
      // 失败原因已由 useAgentEditor 提示。
    }
  }, [saveBindings, hasChanges, bindingsDirty, saveEditor, t]);

  const handleStartChat = useCallback(async () => {
    if (await saveBindings()) {
      await startChat();
    }
  }, [saveBindings, startChat]);

  return {
    hasChanges: hasChanges || bindingsDirty,
    saving: editor.saving || commandBindings.saving,
    handleSave,
    handleStartChat,
  };
}
