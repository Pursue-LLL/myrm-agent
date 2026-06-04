import { describe, expect, it } from 'vitest';

import { buildVisualApprovalOsOverlayPayload } from '@/lib/approval/visualApprovalOsOverlay';

describe('visualApprovalOsOverlay', () => {
  it('builds overlay payload from visual context', () => {
    const payload = buildVisualApprovalOsOverlayPayload({
      base64: 'abc',
      mimeType: 'image/png',
      bbox: { x: 1, y: 2, width: 3, height: 4 },
      viewportWidth: 100,
      viewportHeight: 200,
      targetLabel: 'd1',
      highlightKind: 'ref',
    });

    expect(payload).toEqual({
      x: 1,
      y: 2,
      width: 3,
      height: 4,
      viewportWidth: 100,
      viewportHeight: 200,
      label: 'd1',
    });
  });
});
