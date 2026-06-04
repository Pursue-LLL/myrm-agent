import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useVisualApprovalOsOverlay } from '@/hooks/useVisualApprovalOsOverlay';
import type { ToolApprovalRequest } from '@/store/chat/types';

const showMock = vi.fn().mockResolvedValue(undefined);
const hideMock = vi.fn().mockResolvedValue(undefined);

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => true,
}));

vi.mock('@/lib/approval/visualApprovalOsOverlay', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/approval/visualApprovalOsOverlay')>();
  return {
    ...actual,
    showVisualApprovalOsOverlay: (...args: unknown[]) => showMock(...args),
    hideVisualApprovalOsOverlay: (...args: unknown[]) => hideMock(...args),
  };
});

const desktopRequest: ToolApprovalRequest = {
  requestId: 'req-desktop',
  toolName: 'desktop_interact',
  toolInput: { ref: 'd1' },
  reason: 'Click',
  timeoutSeconds: 60,
  expiresAt: Math.floor(Date.now() / 1000) + 60,
  timeoutBehavior: 'deny',
  messageId: 'msg-1',
  displayMode: 'approval',
  chatId: 'chat-1',
  actionMode: 'agent',
};

const viewData = {
  screenshotBase64: 'abc',
  mimeType: 'image/png',
  refs: {
    d1: {
      bbox: { x: 10, y: 20, width: 30, height: 40, viewport_x: 10, viewport_y: 20 },
    },
  },
  viewportWidth: 1920,
  viewportHeight: 1080,
};

describe('useVisualApprovalOsOverlay', () => {
  beforeEach(() => {
    showMock.mockClear();
    hideMock.mockClear();
  });

  it('shows overlay when a ready desktop target exists', async () => {
    renderHook(() =>
      useVisualApprovalOsOverlay([desktopRequest], viewData, null, false, false, false),
    );

    await waitFor(() => {
      expect(showMock).toHaveBeenCalledWith({
        x: 10,
        y: 20,
        width: 30,
        height: 40,
        viewportWidth: 1920,
        viewportHeight: 1080,
        label: 'd1',
      });
    });
  });

  it('hides overlay when no ready desktop target exists', async () => {
    renderHook(() =>
      useVisualApprovalOsOverlay([desktopRequest], null, null, true, false, false),
    );

    await waitFor(() => {
      expect(showMock).not.toHaveBeenCalled();
      expect(hideMock).toHaveBeenCalled();
    });
  });

  it('hides overlay on cleanup', async () => {
    const { unmount } = renderHook(() =>
      useVisualApprovalOsOverlay([desktopRequest], viewData, null, false, false, false),
    );

    await waitFor(() => expect(showMock).toHaveBeenCalled());
    hideMock.mockClear();
    unmount();

    await waitFor(() => expect(hideMock).toHaveBeenCalled());
  });
});
