import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  buildVisualApprovalOsOverlayPayload,
  showVisualApprovalOsOverlay,
} from '@/lib/approval/visualApprovalOsOverlay';
import { invokeTauriCommand } from '@/lib/tauri';

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => true,
}));

const isMacOSMock = vi.fn(() => true);
const isWindowsMock = vi.fn(() => false);

vi.mock('@/lib/desktopBridge', () => ({
  desktopBridge: {
    isMacOS: () => isMacOSMock(),
    isWindows: () => isWindowsMock(),
  },
}));

vi.mock('@/lib/tauri', () => ({
  invokeTauriCommand: vi.fn().mockResolvedValue({ shown: true, degraded: false }),
}));

describe('visualApprovalOsOverlay', () => {
  beforeEach(() => {
    isMacOSMock.mockReturnValue(true);
    isWindowsMock.mockReturnValue(false);
    (invokeTauriCommand as ReturnType<typeof vi.fn>).mockClear();
  });

  it('builds screen-absolute overlay payload for ref highlights', () => {
    const payload = buildVisualApprovalOsOverlayPayload({
      base64: 'abc',
      mimeType: 'image/png',
      bbox: { x: 500, y: 300, width: 40, height: 30 },
      viewportWidth: 1280,
      viewportHeight: 800,
      screenWidth: 1440,
      screenHeight: 900,
      targetLabel: 'd1',
      highlightKind: 'ref',
    });

    expect(payload).toEqual({
      x: 500,
      y: 300,
      width: 40,
      height: 30,
      viewportWidth: 1280,
      viewportHeight: 800,
      coordinateMode: 'screen',
      screenWidth: 1440,
      screenHeight: 900,
      label: 'd1',
    });
  });

  it('returns null for ref highlights without screen metadata', () => {
    const payload = buildVisualApprovalOsOverlayPayload({
      base64: 'abc',
      mimeType: 'image/png',
      bbox: { x: 1, y: 2, width: 3, height: 4 },
      viewportWidth: 100,
      viewportHeight: 200,
      targetLabel: 'd1',
      highlightKind: 'ref',
    });

    expect(payload).toBeNull();
  });

  it('invokes show IPC on Windows Tauri', async () => {
    isMacOSMock.mockReturnValueOnce(false);
    isWindowsMock.mockReturnValueOnce(true);

    await showVisualApprovalOsOverlay({
      x: 1,
      y: 2,
      width: 3,
      height: 4,
      viewportWidth: 100,
      viewportHeight: 200,
      coordinateMode: 'screen',
      screenWidth: 1440,
      screenHeight: 900,
    });

    expect(invokeTauriCommand).toHaveBeenCalledWith('show_visual_approval_overlay', expect.any(Object));
  });

  it('skips show IPC when not on macOS or Windows', async () => {
    isMacOSMock.mockReturnValueOnce(false);
    isWindowsMock.mockReturnValueOnce(false);

    await showVisualApprovalOsOverlay({
      x: 1,
      y: 2,
      width: 3,
      height: 4,
      viewportWidth: 100,
      viewportHeight: 200,
      coordinateMode: 'screen',
      screenWidth: 1440,
      screenHeight: 900,
    });

    expect(invokeTauriCommand).not.toHaveBeenCalled();
  });

  it('returns IPC show result on macOS Tauri', async () => {
    const result = await showVisualApprovalOsOverlay({
      x: 1,
      y: 2,
      width: 3,
      height: 4,
      viewportWidth: 100,
      viewportHeight: 200,
      coordinateMode: 'screen',
      screenWidth: 1440,
      screenHeight: 900,
    });

    expect(result).toEqual({ shown: true, degraded: false });
  });

  it('builds image-space overlay payload for coordinate highlights', () => {
    const payload = buildVisualApprovalOsOverlayPayload({
      base64: 'abc',
      mimeType: 'image/png',
      bbox: { x: 1, y: 2, width: 48, height: 48 },
      viewportWidth: 100,
      viewportHeight: 200,
      screenWidth: 1440,
      screenHeight: 900,
      targetLabel: '(1, 2)',
      highlightKind: 'coordinate',
    });

    expect(payload).toEqual({
      x: 1,
      y: 2,
      width: 48,
      height: 48,
      viewportWidth: 100,
      viewportHeight: 200,
      coordinateMode: 'image',
      screenWidth: 1440,
      screenHeight: 900,
      label: '(1, 2)',
    });
  });
});
