import { describe, expect, it } from 'vitest';

import {
  resolveDesktopOverlayTarget,
  selectEarliestInlineRequest,
} from '@/lib/approval/resolveDesktopOverlayTarget';
import type { ToolApprovalRequest } from '@/store/chat/types';

const baseRequest: ToolApprovalRequest = {
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
  viewportWidth: 1280,
  viewportHeight: 800,
  screenWidth: 1440,
  screenHeight: 900,
};

describe('resolveDesktopOverlayTarget', () => {
  it('selects the earliest expiring inline request', () => {
    const later = { ...baseRequest, requestId: 'later', expiresAt: baseRequest.expiresAt + 30 };
    const earlier = { ...baseRequest, requestId: 'earlier', expiresAt: baseRequest.expiresAt - 10 };

    expect(selectEarliestInlineRequest([later, earlier])).toEqual(earlier);
  });

  it('returns ready desktop overlay payload for the earliest expiring desktop request', () => {
    const laterDesktop = {
      ...baseRequest,
      requestId: 'later-desktop',
      expiresAt: baseRequest.expiresAt + 30,
    };
    const earlierDesktop = {
      ...baseRequest,
      requestId: 'earlier-desktop',
      expiresAt: baseRequest.expiresAt - 10,
    };

    const target = resolveDesktopOverlayTarget({
      inlineRequests: [laterDesktop, earlierDesktop],
      desktopViewData: viewData,
      browserViewData: null,
      desktopLoading: false,
      browserLoading: false,
      snapshotFetchFailed: false,
    });

    expect(target?.request.requestId).toBe('earlier-desktop');
    expect(target?.payload).toEqual({
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

  it('returns null when screen metadata is missing for ref highlights', () => {
    const target = resolveDesktopOverlayTarget({
      inlineRequests: [baseRequest],
      desktopViewData: {
        ...viewData,
        screenWidth: undefined,
        screenHeight: undefined,
      },
      browserViewData: null,
      desktopLoading: false,
      browserLoading: false,
      snapshotFetchFailed: false,
    });

    expect(target).toBeNull();
  });

  it('returns null while desktop snapshot is still loading', () => {
    const target = resolveDesktopOverlayTarget({
      inlineRequests: [baseRequest],
      desktopViewData: null,
      browserViewData: null,
      desktopLoading: true,
      browserLoading: false,
      snapshotFetchFailed: false,
    });

    expect(target).toBeNull();
  });

  it('skips non-ready desktop requests and picks the next ready one', () => {
    const missingRef = {
      ...baseRequest,
      requestId: 'missing-ref',
      toolInput: { ref: 'missing' },
      expiresAt: baseRequest.expiresAt - 20,
    };
    const ready = {
      ...baseRequest,
      requestId: 'ready',
      expiresAt: baseRequest.expiresAt - 10,
    };

    const target = resolveDesktopOverlayTarget({
      inlineRequests: [missingRef, ready],
      desktopViewData: viewData,
      browserViewData: null,
      desktopLoading: false,
      browserLoading: false,
      snapshotFetchFailed: false,
    });

    expect(target?.request.requestId).toBe('ready');
  });
});
