/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../ChatWindowSatellites (POS: 聊天窗口的悬浮入口与抽屉集合)
 * - @/store/useChatStore, useBrowserInspectorStore, useDesktopInspectorStore (POS: 会话 id、恢复对话框、检查器面板开关)
 *
 * [OUTPUT]
 * Vitest: 会话 id 取 store 优先、回退 props；两个实时视图各收到自己的指令回调；切换会话关闭已打开的检查器面板；
 * 上下文检查器由全局事件打开；恢复对话框只在有 agent 时出现；撤销按钮只属于已保存的会话。
 *
 * [POS]
 * next/dynamic 按加载器源码替身为带属性探针的最小组件，真实 store 与 useClosePanelOnChatSwitch 保持不变。
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Message } from '@/store/chat/types';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useChatStore from '@/store/useChatStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';

const probe = vi.hoisted(() => ({
  presence: vi.fn<(chatId: string, hasContent: boolean) => void>(),
  subagentDashboard: vi.fn<(props: { chatId?: string }) => void>(),
}));

vi.mock('@/hooks/chat/usePresenceReadMark', () => ({ usePresenceReadMark: probe.presence }));
vi.mock('../subagent/SubagentDashboard', () => ({
  default: (props: { chatId?: string }) => {
    probe.subagentDashboard(props);
    return null;
  },
}));
vi.mock('@/components/features/desktop-inspector/DesktopControlApprovalOverlay', () => ({ default: () => null }));

type InstructionHandler = (instruction: string, refId: string | null) => void;

vi.mock('next/dynamic', () => ({
  default: (loader: () => Promise<unknown>) => {
    const source = String(loader);
    if (source.includes('BrowserLiveView')) {
      return ({ onSendInstruction }: { onSendInstruction: InstructionHandler }) => (
        <button type="button" onClick={() => onSendInstruction('look here', 'e12')}>
          browser live view
        </button>
      );
    }
    if (source.includes('DesktopLiveView')) {
      return ({ onSendInstruction }: { onSendInstruction: InstructionHandler }) => (
        <button type="button" onClick={() => onSendInstruction('click it', 'w3')}>
          desktop live view
        </button>
      );
    }
    if (source.includes('ContextFootprintInspector')) {
      return ({ open, onClose }: { open: boolean; onClose: () => void }) =>
        open ? (
          <button type="button" onClick={onClose}>
            context inspector
          </button>
        ) : null;
    }
    if (source.includes('StartupRecoveryDialog')) {
      return ({
        agentId,
        open,
        onOpenChange,
      }: {
        agentId: string;
        open: boolean;
        onOpenChange: (open: boolean) => void;
      }) => (
        <div data-testid="recovery" data-open={String(open)}>
          <span>{agentId}</span>
          <button type="button" onClick={() => onOpenChange(true)}>
            stay open
          </button>
          <button type="button" onClick={() => onOpenChange(false)}>
            dismiss
          </button>
        </div>
      );
    }
    if (source.includes('SessionRevertButton')) {
      return ({ sessionId }: { sessionId: string }) => <span data-testid="revert-button">{sessionId}</span>;
    }
    if (source.includes('PreferenceRadarToggle')) {
      return ({ chatId }: { chatId?: string }) => <span data-testid="radar">{chatId ?? 'no chat'}</span>;
    }
    return () => null;
  },
}));

import ChatWindowSatellites from '../ChatWindowSatellites';

const FIRST_MESSAGE: Message = {
  messageId: 'message-1',
  chatId: 'chat-1',
  role: 'user',
  content: 'hello',
  createdAt: new Date(),
};

const onInspectorInstruction = vi.fn<InstructionHandler>();
const onDesktopInspectorInstruction = vi.fn<InstructionHandler>();

function renderSatellites(chatId?: string) {
  return render(
    <ChatWindowSatellites
      chatId={chatId}
      onInspectorInstruction={onInspectorInstruction}
      onDesktopInspectorInstruction={onDesktopInspectorInstruction}
    />,
  );
}

describe('ChatWindowSatellites wiring', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.setState({
      chatId: 'chat-1',
      messages: [],
      recoveryDialogOpen: false,
      recoveryAgentId: null,
    });
    useBrowserInspectorStore.setState({ isOpen: false });
    useDesktopInspectorStore.setState({ isOpen: false });
  });

  afterEach(() => {
    useBrowserInspectorStore.setState({ isOpen: false, instructionText: '' });
    useDesktopInspectorStore.setState({ isOpen: false });
  });

  it('gives each live view the handler of its own inspector', () => {
    renderSatellites('chat-1');

    fireEvent.click(screen.getByText('browser live view'));
    expect(onInspectorInstruction).toHaveBeenCalledExactlyOnceWith('look here', 'e12');
    expect(onDesktopInspectorInstruction).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText('desktop live view'));
    expect(onDesktopInspectorInstruction).toHaveBeenCalledExactlyOnceWith('click it', 'w3');
    expect(onInspectorInstruction).toHaveBeenCalledOnce();
  });

  describe('context footprint inspector', () => {
    it('opens on the global event and closes from the panel', () => {
      renderSatellites('chat-1');
      expect(screen.queryByText('context inspector')).toBeNull();

      act(() => {
        window.dispatchEvent(new Event('myrm:open-context-inspector'));
      });
      fireEvent.click(screen.getByText('context inspector'));

      expect(screen.queryByText('context inspector')).toBeNull();
    });

    it('stops listening for the event once unmounted', () => {
      const removeListener = vi.spyOn(window, 'removeEventListener');
      const { unmount } = renderSatellites('chat-1');

      unmount();

      expect(removeListener).toHaveBeenCalledWith('myrm:open-context-inspector', expect.any(Function));
      removeListener.mockRestore();
    });
  });

  describe('session-bound launchers', () => {
    it('offers the revert button and the preference radar for a saved chat with messages', () => {
      useChatStore.setState({ messages: [FIRST_MESSAGE] });
      renderSatellites('chat-1');

      expect(screen.getByTestId('revert-button').textContent).toBe('chat-1');
      expect(screen.getByTestId('radar').textContent).toBe('chat-1');
      expect(probe.subagentDashboard).toHaveBeenLastCalledWith({ chatId: 'chat-1' });
    });

    it('offers neither without a chat id or messages', () => {
      renderSatellites();

      expect(screen.queryByTestId('revert-button')).toBeNull();
      expect(screen.queryByTestId('radar')).toBeNull();
      expect(probe.subagentDashboard).toHaveBeenLastCalledWith({ chatId: undefined });
    });
  });

  describe('startup recovery dialog', () => {
    it('is absent while closed or without an agent to recover', () => {
      renderSatellites('chat-1');
      expect(screen.queryByTestId('recovery')).toBeNull();

      act(() => useChatStore.setState({ recoveryDialogOpen: true, recoveryAgentId: null }));
      expect(screen.queryByTestId('recovery')).toBeNull();

      act(() => useChatStore.setState({ recoveryDialogOpen: false, recoveryAgentId: 'agent-7' }));
      expect(screen.queryByTestId('recovery')).toBeNull();
    });

    it('shows for the agent and clears the store only when it is dismissed', () => {
      renderSatellites('chat-1');

      act(() => useChatStore.getState().openRecoveryDialog('agent-7'));
      const dialog = screen.getByTestId('recovery');
      expect(dialog.getAttribute('data-open')).toBe('true');
      expect(dialog.textContent).toContain('agent-7');

      fireEvent.click(screen.getByText('stay open'));
      expect(useChatStore.getState().recoveryDialogOpen).toBe(true);

      fireEvent.click(screen.getByText('dismiss'));
      expect(useChatStore.getState().recoveryDialogOpen).toBe(false);
      expect(useChatStore.getState().recoveryAgentId).toBeNull();
      expect(screen.queryByTestId('recovery')).toBeNull();
    });
  });

  describe('open chat identity', () => {
    it('prefers the chat the store holds, trimmed, and tells the presence mark whether it has messages', () => {
      useChatStore.setState({ chatId: '  store-chat  ', messages: [FIRST_MESSAGE] });
      renderSatellites('prop-chat');

      expect(probe.presence).toHaveBeenLastCalledWith('store-chat', true);
    });

    it('falls back to the chat id of the route while the store holds none', () => {
      useChatStore.setState({ chatId: undefined, messages: [] });
      renderSatellites('  prop-chat ');

      expect(probe.presence).toHaveBeenLastCalledWith('prop-chat', false);
    });

    it('closes both open inspector panels when the user moves to another chat', () => {
      useBrowserInspectorStore.setState({ isOpen: true });
      useDesktopInspectorStore.setState({ isOpen: true });
      renderSatellites('chat-1');

      act(() => useChatStore.setState({ chatId: 'chat-1' }));
      expect(useBrowserInspectorStore.getState().isOpen).toBe(true);
      expect(useDesktopInspectorStore.getState().isOpen).toBe(true);

      act(() => useChatStore.setState({ chatId: 'chat-2' }));
      expect(useBrowserInspectorStore.getState().isOpen).toBe(false);
      expect(useDesktopInspectorStore.getState().isOpen).toBe(false);
    });

    it('leaves the draft of a panel that is not open alone', () => {
      useDesktopInspectorStore.setState({ isOpen: true });
      useBrowserInspectorStore.setState({ isOpen: false, instructionText: 'draft' });
      renderSatellites('chat-1');

      act(() => useChatStore.setState({ chatId: 'chat-2' }));

      expect(useDesktopInspectorStore.getState().isOpen).toBe(false);
      expect(useBrowserInspectorStore.getState().instructionText).toBe('draft');
    });
  });
});
