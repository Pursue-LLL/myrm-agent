import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

const isCompanionEnabledMock = vi.fn(() => true);

vi.mock('@/store/useFeatureGateStore', () => ({
  useFeatureGateStore: (selector: (s: { isEnabled: (key: string) => boolean }) => unknown) =>
    selector({ isEnabled: (key: string) => (key === 'companion_mode' ? isCompanionEnabledMock() : false) }),
}));

vi.mock('../SubagentDashboard', () => ({
  default: () => null,
}));

vi.mock('@/components/features/desktop-inspector/DesktopControlApprovalOverlay', () => ({
  default: () => null,
}));

const petOverlayRenderMock = vi.fn(() => <div data-testid="pet-overlay" />);
const petPaletteRenderMock = vi.fn(() => <div data-testid="pet-palette" />);

vi.mock('next/dynamic', () => ({
  default: (loader: () => Promise<{ default: React.ComponentType }>) => {
    const loaderStr = String(loader);
    if (loaderStr.includes('PetOverlay')) {
      return () => petOverlayRenderMock();
    }
    if (loaderStr.includes('PetPalette')) {
      return () => petPaletteRenderMock();
    }
    return () => null;
  },
}));

import ChatWindowSatellites from '../ChatWindowSatellites';

describe('ChatWindowSatellites companion_mode gate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    isCompanionEnabledMock.mockReturnValue(true);
  });

  it('mounts PetOverlay and PetPalette when companion_mode is enabled', () => {
    render(
      <ChatWindowSatellites
        chatId="chat-1"
        onInspectorInstruction={() => {}}
        onDesktopInspectorInstruction={() => {}}
      />,
    );
    expect(petOverlayRenderMock).toHaveBeenCalled();
    expect(petPaletteRenderMock).toHaveBeenCalled();
  });

  it('does not mount PetOverlay or PetPalette when companion_mode is disabled', () => {
    isCompanionEnabledMock.mockReturnValue(false);
    render(
      <ChatWindowSatellites
        chatId="chat-1"
        onInspectorInstruction={() => {}}
        onDesktopInspectorInstruction={() => {}}
      />,
    );
    expect(petOverlayRenderMock).not.toHaveBeenCalled();
    expect(petPaletteRenderMock).not.toHaveBeenCalled();
  });
});
