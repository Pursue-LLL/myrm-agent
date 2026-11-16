/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/store/chat/types::ActionMode, BuiltinToolId, ToolSnapshotItem (POS: @/store/chat/types 稳定入口；实现位于 types/。)
 * - @/store/useToolsSnapshotStore::useToolsSnapshotStore
 * - @/components/dev/e2eBridge/hostEnv::prepareAutomationSend (POS: 开发桥的页面环境探针)
 * - @/components/dev/e2eBridge/members/types::E2eBridgeMembers (POS: 桥成员分组的类型)
 *
 * [OUTPUT]
 * - createComposerMembers(): builtin tools, action mode, search depth, browser source and computer-use readiness
 *
 * [POS]
 * 桥成员（输入区设置）：内置工具、动作模式、搜索深度、浏览器来源与桌面控制就绪。
 */
import { flushSync } from 'react-dom';
import useChatStore from '@/store/useChatStore';
import type { ActionMode, BuiltinToolId, ToolSnapshotItem } from '@/store/chat/types';
import useToolsSnapshotStore from '@/store/useToolsSnapshotStore';
import { prepareAutomationSend } from '@/components/dev/e2eBridge/hostEnv';
import type { E2eBridgeMembers } from '@/components/dev/e2eBridge/members/types';

export function createComposerMembers(): E2eBridgeMembers {
  return {
    setCurrentBuiltinTools: (tools: string[]) => {
      const nextTools = tools as BuiltinToolId[];
      flushSync(() => {
        useChatStore.getState().setCurrentBuiltinTools([...nextTools]);
      });
    },
    getCurrentBuiltinTools: () => [...useChatStore.getState().currentBuiltinTools],
    setToolsSnapshotForE2e: (tools: ToolSnapshotItem[]) => {
      useToolsSnapshotStore.getState().setTools(tools);
    },
    setBrowserSource: (source: string) => {
      flushSync(() => {
        const chat = useChatStore.getState();
        if (chat.agentConfig) {
          chat.updateAgentConfig({ browserSource: source });
          return;
        }
        chat.setAgentConfig({
          browserSource: source,
          enabledBuiltinTools: [...chat.currentBuiltinTools],
          selectedSkillIds: [],
          selectedMcpNames: [],
          systemPrompt: '',
          useGlobalInstruction: true,
        });
      });
    },
    getBrowserSource: () => useChatStore.getState().agentConfig?.browserSource ?? null,
    ensureComputerUseReady: () => {
      flushSync(() => {
        prepareAutomationSend();
        const chat = useChatStore.getState();
        const tools = chat.currentBuiltinTools.includes('computer_use')
          ? chat.currentBuiltinTools
          : [...chat.currentBuiltinTools, 'computer_use' as BuiltinToolId];
        chat.setCurrentBuiltinTools([...tools]);
      });
      void import('@/store/useDesktopInspectorStore').then(({ default: useDesktopInspectorStore }) => {
        useDesktopInspectorStore.getState().openPanel();
      });
    },
    getActionMode: () => useChatStore.getState().actionMode,
    setActionMode: (mode: ActionMode) => {
      flushSync(() => {
        useChatStore.getState().setActionMode(mode);
      });
    },
    getSearchDepth: () => useChatStore.getState().searchDepth,
    setSearchDepth: (depth: 'normal' | 'deep') => {
      flushSync(() => {
        useChatStore.getState().setSearchDepth(depth);
      });
    },
  } as E2eBridgeMembers;
}
