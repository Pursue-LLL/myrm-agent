import { describe, expect, it } from 'vitest';

import {
  hasVisualApprovalContext,
  resolveVisualApprovalContext,
  type InspectorViewSnapshot,
} from '@/lib/approval/visualApprovalContext';
import type { ToolApprovalRequest } from '@/store/chat/types';

const viewData: InspectorViewSnapshot = {
  screenshotBase64: 'abc123',
  mimeType: 'image/jpeg',
  viewportWidth: 1920,
  viewportHeight: 1080,
  refs: {
    e1: {
      role: 'button',
      name: 'Delete',
      nth: null,
      bbox: {
        x: 100,
        y: 5900,
        width: 80,
        height: 32,
        centerX: 140,
        centerY: 5916,
        viewport_x: 100,
        viewport_y: 200,
        viewport_width: 80,
        viewport_height: 32,
      },
      position: null,
    },
  },
};

describe('resolveVisualApprovalContext', () => {
  it('prefers viewport coordinates for ref-based browser approvals', () => {
    const context = resolveVisualApprovalContext(
      'browser_click',
      { ref: 'e1' },
      null,
      viewData,
    );

    expect(context).not.toBeNull();
    expect(context?.bbox).toEqual({
      x: 100,
      y: 200,
      width: 80,
      height: 32,
    });
    expect(context?.highlightKind).toBe('ref');
  });

  it('builds coordinate highlight for desktop vision actions', () => {
    const context = resolveVisualApprovalContext(
      'desktop_vision_tool',
      { action: 'left_click', coordinate: [960, 540] },
      viewData,
      null,
    );

    expect(context).not.toBeNull();
    expect(context?.highlightKind).toBe('coordinate');
    expect(context?.bbox.width).toBe(48);
    expect(context?.bbox.height).toBe(48);
    expect(context?.bbox.x).toBe(936);
    expect(context?.bbox.y).toBe(516);
    expect(context?.targetLabel).toBe('(960, 540)');
  });

  it('returns null for unrelated tools', () => {
    const context = resolveVisualApprovalContext('file_write_tool', { path: 'a.txt' }, viewData, viewData);
    expect(context).toBeNull();
  });
});

describe('hasVisualApprovalContext', () => {
  it('detects pending visual approvals from queue requests', () => {
    const request: ToolApprovalRequest = {
      requestId: 'req-1',
      toolName: 'desktop_interact_tool',
      toolInput: { ref: 'e1', action: 'click' },
      reason: 'Sensitive click',
      timeoutSeconds: 60,
      expiresAt: Math.floor(Date.now() / 1000) + 60,
      timeoutBehavior: 'deny',
      messageId: 'msg-1',
      displayMode: 'approval',
      chatId: 'chat-1',
      actionMode: 'agent',
    };

    expect(hasVisualApprovalContext(request, viewData, null)).toBe(true);
  });
});
