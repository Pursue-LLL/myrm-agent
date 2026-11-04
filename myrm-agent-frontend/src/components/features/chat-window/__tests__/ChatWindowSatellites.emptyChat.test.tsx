/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../ChatWindowSatellites (POS: 聊天窗口的悬浮入口与抽屉集合)
 * - @/store/useChatStore::messages (POS: 空会话判定)
 *
 * [OUTPUT]
 * Vitest: 空会话不挂出会盖住首屏内容的悬浮入口，会话有消息后恢复。
 *
 * [POS]
 * next/dynamic 按加载器路径替身，只探测这两个悬浮入口收到的属性与挂载情况。
 */
import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

const visualDesktopRender = vi.fn<(props: { hideLauncher?: boolean }) => void>();
const preferenceRadarRender = vi.fn<() => void>();

vi.mock('../subagent/SubagentDashboard', () => ({ default: () => null }));

vi.mock('@/components/features/desktop-inspector/DesktopControlApprovalOverlay', () => ({
  default: () => null,
}));

vi.mock('next/dynamic', () => ({
  default: (loader: () => Promise<unknown>) => {
    const source = String(loader);
    if (source.includes('VisualDesktopToggle')) {
      return (props: { hideLauncher?: boolean }) => {
        visualDesktopRender(props);
        return null;
      };
    }
    if (source.includes('PreferenceRadarToggle')) {
      return () => {
        preferenceRadarRender();
        return null;
      };
    }
    return () => null;
  },
}));

import ChatWindowSatellites from '../ChatWindowSatellites';

const firstMessage: Message = {
  messageId: 'message-1',
  chatId: 'chat-1',
  role: 'user',
  content: 'hello',
  createdAt: new Date(),
};

function renderSatellites() {
  return render(
    <ChatWindowSatellites chatId="chat-1" onInspectorInstruction={() => {}} onDesktopInspectorInstruction={() => {}} />,
  );
}

describe('ChatWindowSatellites on an empty chat', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.setState({ messages: [] });
  });

  afterEach(() => {
    useChatStore.setState({ messages: [] });
  });

  it('keeps the floating launchers off the first screen', () => {
    renderSatellites();

    expect(visualDesktopRender).toHaveBeenLastCalledWith(expect.objectContaining({ hideLauncher: true }));
    expect(preferenceRadarRender).not.toHaveBeenCalled();
  });

  it('brings both launchers back once the chat has messages', () => {
    renderSatellites();

    act(() => useChatStore.setState({ messages: [firstMessage] }));

    expect(visualDesktopRender).toHaveBeenLastCalledWith(expect.objectContaining({ hideLauncher: false }));
    expect(preferenceRadarRender).toHaveBeenCalled();
  });
});
