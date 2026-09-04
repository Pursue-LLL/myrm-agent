/** @vitest-environment jsdom */
'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import DeviceLiveView from '../DeviceLiveView';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector?: (state: { chatId: string }) => unknown) => {
    const state = { chatId: 'chat-test' };
    return typeof selector === 'function' ? selector(state) : state;
  },
}));

vi.mock('@/store/useDeviceInspectorStore', () => {
  return {
    default: () => ({
      isOpen: true,
      mode: 'view',
      viewData: {
        screenshotBase64: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
        mimeType: 'image/png',
        refs: {},
        deviceId: 'emulator-5554',
        deviceName: 'Pixel 8 Pro (ADB)',
        platform: 'android',
        connected: true,
        notificationRedaction: true,
        viewportWidth: 1080,
        viewportHeight: 2400,
        sourceChatId: 'chat-test',
        updatedAt: Date.now(),
      },
      selectedElement: null,
      instructionText: '',
      isSnapshotLoading: false,
      notificationRedaction: true,
      closePanel: vi.fn(),
      setMode: vi.fn(),
      setNotificationRedaction: vi.fn(),
      selectElement: vi.fn(),
      clearSelection: vi.fn(),
      setInstructionText: vi.fn(),
      fetchSnapshot: vi.fn(),
      sendTouchRelay: vi.fn(),
    }),
    selectScopedDeviceViewData: (viewData: unknown) => viewData,
  };
});

describe('DeviceLiveView', () => {
  it('renders device inspector panel with screenshot and redacted notification badge', () => {
    render(<DeviceLiveView onSendInstruction={vi.fn()} />);

    expect(screen.getByTestId('device-inspector-panel')).toBeInTheDocument();
    expect(screen.getByText('Pixel 8 Pro (ADB)')).toBeInTheDocument();
    expect(screen.getByText('notificationRedacted')).toBeInTheDocument();
  });
});
