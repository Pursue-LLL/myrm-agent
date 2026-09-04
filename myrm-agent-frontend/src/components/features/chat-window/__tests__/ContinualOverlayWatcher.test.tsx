/** @vitest-environment jsdom */

import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ContinualOverlayWatcher } from '../ContinualOverlayWatcher';
import * as chatService from '@/services/chat';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/services/chat', () => ({
  getSessionOverlays: vi.fn(),
  rollbackSessionOverlay: vi.fn(),
}));

describe('ContinualOverlayWatcher', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when there are no active overlays', async () => {
    vi.mocked(chatService.getSessionOverlays).mockResolvedValueOnce([]);
    const { container } = render(<ContinualOverlayWatcher chatId="test-chat" />);
    await waitFor(() => {
      expect(chatService.getSessionOverlays).toHaveBeenCalledWith('test-chat');
    });
    expect(container.firstChild).toBeNull();
  });

  it('renders ContinualOverlayBadge when active overlays exist', async () => {
    vi.mocked(chatService.getSessionOverlays).mockResolvedValueOnce([
      {
        overlayId: 'ovl-watcher-1',
        shellType: 'skill_variant',
        triggerReason: 'test-reason',
        remainingTurns: 3,
        advisoryText: 'test advisory',
      },
    ]);

    render(<ContinualOverlayWatcher chatId="test-chat-with-overlay" />);
    await waitFor(() => {
      expect(screen.getByText('test advisory')).toBeInTheDocument();
    });
  });
});
