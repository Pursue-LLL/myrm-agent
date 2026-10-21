import { describe, expect, it } from 'vitest';

import { resolveVisualApprovalRenderState } from '@/lib/approval/visualApprovalRenderState';
import type { ToolApprovalRequest } from '@/store/chat/types';

function makeRequest(overrides: Partial<ToolApprovalRequest>): ToolApprovalRequest {
  return {
    requestId: 'req-1',
    toolName: 'desktop_interact',
    toolInput: { ref: 'e1' },
    reason: 'test',
    timeoutSeconds: 60,
    expiresAt: Date.now() + 60_000,
    timeoutBehavior: 'deny',
    messageId: 'msg-1',
    displayMode: 'approval',
    chatId: 'chat-1',
    actionMode: 'agent',
    ...overrides,
  };
}

describe('resolveVisualApprovalRenderState', () => {
  it('returns ready when visual context resolves', () => {
    const state = resolveVisualApprovalRenderState({
      request: makeRequest({}),
      desktopViewData: {
        screenshotBase64: 'abc',
        mimeType: 'image/jpeg',
        refs: {
          e1: {
            role: 'button',
            name: 'Delete',
            nth: null,
            bbox: {
              x: 1,
              y: 2,
              width: 3,
              height: 4,
              centerX: 2,
              centerY: 4,
              viewport_x: 10,
              viewport_y: 20,
              viewport_width: 3,
              viewport_height: 4,
            },
            position: null,
          },
        },
        viewportWidth: 100,
        viewportHeight: 100,
      },
      browserViewData: null,
      desktopLoading: false,
      browserLoading: false,
      snapshotFetchFailed: false,
    });

    expect(state.phase).toBe('ready');
    expect(state.visualContext?.bbox).toEqual({
      x: 10,
      y: 20,
      width: 3,
      height: 4,
    });
  });

  it('returns loading while snapshot fetch is in progress', () => {
    const state = resolveVisualApprovalRenderState({
      request: makeRequest({}),
      desktopViewData: null,
      browserViewData: null,
      desktopLoading: true,
      browserLoading: false,
      snapshotFetchFailed: false,
    });

    expect(state.phase).toBe('loading');
  });

  it('returns permission unavailable when desktop needs permission', () => {
    const state = resolveVisualApprovalRenderState({
      request: makeRequest({}),
      desktopViewData: {
        screenshotBase64: '',
        mimeType: 'image/jpeg',
        refs: {},
        viewportWidth: 0,
        viewportHeight: 0,
        needsPermission: true,
      },
      browserViewData: null,
      desktopLoading: false,
      browserLoading: false,
      snapshotFetchFailed: false,
    });

    expect(state.phase).toBe('unavailable');
    expect(state.unavailableReason).toBe('permission');
  });

  it('returns unavailable with fallback when snapshot fetch failed', () => {
    const state = resolveVisualApprovalRenderState({
      request: makeRequest({ toolName: 'browser_click', toolInput: { ref: 'e1' } }),
      desktopViewData: null,
      browserViewData: null,
      desktopLoading: false,
      browserLoading: false,
      snapshotFetchFailed: true,
    });

    expect(state.phase).toBe('unavailable');
    expect(state.unavailableReason).toBe('fetch_failed');
  });
});
