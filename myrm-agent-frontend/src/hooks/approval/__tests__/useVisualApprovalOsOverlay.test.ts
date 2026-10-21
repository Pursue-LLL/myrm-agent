import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useVisualApprovalOsOverlay } from '@/hooks/approval/useVisualApprovalOsOverlay';
import type { InspectorViewSnapshot } from '@/lib/approval/visualApprovalContext';
import type { ToolApprovalRequest } from '@/store/chat/types';

const showMock = vi.fn().mockResolvedValue({ shown: true, degraded: false });
const hideMock = vi.fn().mockResolvedValue(undefined);

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => true,
}));

vi.mock('@/lib/approval/visualApprovalOsOverlay', async () => {
  const actual = await vi.importActual<typeof import('@/lib/approval/visualApprovalOsOverlay')>(
    '@/lib/approval/visualApprovalOsOverlay',
  );
  return {
    ...actual,
    showVisualApprovalOsOverlay: (...args: unknown[]) => showMock(...args),
    hideVisualApprovalOsOverlay: (...args: unknown[]) => hideMock(...args),
  };
});

vi.mock('@/lib/approval/visualApprovalOsOverlaySurface', () => ({
  resetVisualApprovalOsOverlaySurface: vi.fn(),
  setVisualApprovalOsOverlaySurface: vi.fn(),
}));

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

const viewData: InspectorViewSnapshot = {
  screenshotBase64: 'abc',
  mimeType: 'image/png',
  refs: {
    d1: {
      role: 'button',
      name: 'd1',
      nth: 1,
      position: null,
      bbox: {
        x: 10,
        y: 20,
        width: 30,
        height: 40,
        centerX: 25,
        centerY: 40,
        viewport_x: 10,
        viewport_y: 20,
        viewport_width: 30,
        viewport_height: 40,
      },
    },
  },
  viewportWidth: 1280,
  viewportHeight: 800,
  screenWidth: 1440,
  screenHeight: 900,
};

describe('useVisualApprovalOsOverlay', () => {
  beforeEach(() => {
    showMock.mockClear();
    hideMock.mockClear();
  });

  it('shows overlay when a ready desktop target exists', async () => {
    renderHook(() => useVisualApprovalOsOverlay([desktopRequest], viewData, null, false, false, false));

    await waitFor(() => {
      expect(showMock).toHaveBeenCalledWith({
        x: 10,
        y: 20,
        width: 30,
        height: 40,
        viewportWidth: 1280,
        viewportHeight: 800,
        coordinateMode: 'screen',
        screenWidth: 1440,
        screenHeight: 900,
        label: 'd1',
      });
    });
  });

  it('hides overlay when no ready desktop target exists', async () => {
    renderHook(() => useVisualApprovalOsOverlay([desktopRequest], null, null, true, false, false));

    await waitFor(() => {
      expect(showMock).not.toHaveBeenCalled();
      expect(hideMock).toHaveBeenCalled();
    });
  });

  it('does not hide overlay when snapshot deps update while target stays ready', async () => {
    const { rerender } = renderHook(
      ({ loading }) =>
        useVisualApprovalOsOverlay([desktopRequest], viewData, null, loading, false, false),
      { initialProps: { loading: false } },
    );

    await waitFor(() => expect(showMock).toHaveBeenCalled());
    hideMock.mockClear();
    showMock.mockClear();

    rerender({ loading: true });

    await waitFor(() => expect(showMock).toHaveBeenCalled());
    expect(hideMock).not.toHaveBeenCalled();
  });

  it('hides overlay on unmount', async () => {
    const { unmount } = renderHook(() =>
      useVisualApprovalOsOverlay([desktopRequest], viewData, null, false, false, false),
    );

    await waitFor(() => expect(showMock).toHaveBeenCalled());
    hideMock.mockClear();
    unmount();

    await waitFor(() => expect(hideMock).toHaveBeenCalled());
  });
});
