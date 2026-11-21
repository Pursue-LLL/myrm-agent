/**
 * Tests for the Desktop Inspector refresh: it asks for the open chat's own desktop session, an automatic refresh
 * reads the agent's registry view, and only a manual refresh captures the accessibility tree again.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiRequest, chatState } = vi.hoisted(() => ({
  apiRequest: vi.fn(),
  chatState: { chatId: 'chat-1' as string | null },
}));

vi.mock('@/lib/api', () => ({ apiRequest }));
vi.mock('@/store/useChatStore', () => ({ default: { getState: () => chatState } }));

import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';

const SNAPSHOT = {
  screenshot_base64: 'shot',
  mime_type: 'image/jpeg',
  refs: {},
  app_name: 'Calculator',
  window_title: 'Calculator',
  scope: 'foreground',
  needs_permission: false,
  viewport_width: 100,
  viewport_height: 100,
};

describe('useDesktopInspectorStore fetchSnapshot', () => {
  beforeEach(() => {
    useDesktopInspectorStore.getState().reset();
    apiRequest.mockReset();
    apiRequest.mockResolvedValue(SNAPSHOT);
    chatState.chatId = 'chat-1';
  });

  it('an automatic refresh reads the registry view of the open chat', async () => {
    await useDesktopInspectorStore.getState().fetchSnapshot(true);

    expect(apiRequest).toHaveBeenCalledOnce();
    expect(apiRequest).toHaveBeenCalledWith('/webui/desktop/snapshot?source=registry&chat_id=chat-1', { silent: true });
  });

  it.each([[false], [undefined]])('a manual refresh (%s) captures again for the open chat', async (isTurnView) => {
    await useDesktopInspectorStore.getState().fetchSnapshot(isTurnView);

    expect(apiRequest).toHaveBeenCalledWith('/webui/desktop/snapshot?source=live&chat_id=chat-1', { silent: true });
  });

  it('marks the view with the chat and with who asked for it', async () => {
    await useDesktopInspectorStore.getState().fetchSnapshot(true);

    expect(useDesktopInspectorStore.getState().viewData).toMatchObject({ sourceChatId: 'chat-1', isTurnView: true });
  });

  it('asks nothing without an open chat', async () => {
    chatState.chatId = null;

    const fetched = await useDesktopInspectorStore.getState().fetchSnapshot(true);

    expect(fetched).toBe(false);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});
