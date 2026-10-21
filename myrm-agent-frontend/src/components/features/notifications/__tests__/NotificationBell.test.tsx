/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockPush = vi.fn();
const apiRequestMock = vi.fn();

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
}));

vi.mock('@/store/useAuthStore', () => ({
  __esModule: true,
  default: (selector: (state: { isAuthenticated: boolean }) => boolean) => selector({ isAuthenticated: true }),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import NotificationBell from '../NotificationBell';

describe('NotificationBell action routing', () => {
  beforeEach(() => {
    mockPush.mockReset();
    apiRequestMock.mockReset();
  });

  it('pushes action_url when alert is clicked', async () => {
    apiRequestMock.mockImplementation((path: string) => {
      if (path === '/notifications?limit=20') {
        return Promise.resolve({
          items: [
            {
              id: 'notif-1',
              title: 'Wiki alert',
              message: 'Low deep verification rate',
              type: 'warning',
              source: 'wiki_evidence',
              is_read: false,
              created_at: '2026-07-27T00:00:00Z',
              meta_data: {
                action_url: '/settings/developer?sub=usage',
              },
            },
          ],
          total: 1,
          unread_count: 1,
        });
      }
      if (path === '/notifications/notif-1/read') {
        return Promise.resolve({ status: 'ok' });
      }
      return Promise.resolve({});
    });

    render(<NotificationBell />);
    await waitFor(() => expect(apiRequestMock).toHaveBeenCalledWith('/notifications?limit=20'));

    fireEvent.click(screen.getByRole('button', { name: 'title' }));
    await waitFor(() => expect(screen.getByText('Wiki alert')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Wiki alert'));

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/settings/developer?sub=usage'));
    expect(apiRequestMock).toHaveBeenCalledWith('/notifications/notif-1/read', { method: 'POST' });
  });

  it('renders catalog-key copy through the translator so the bell is localized', async () => {
    apiRequestMock.mockImplementation((path: string) => {
      if (path === '/notifications?limit=20') {
        return Promise.resolve({
          items: [
            {
              id: 'notif-2',
              title: 'Message delivery failed',
              message: 'Delivery to telegram failed permanently.',
              type: 'error',
              source: 'channel_gateway',
              is_read: false,
              created_at: '2026-10-18T00:00:00Z',
              meta_data: {
                delivery_id: 'd1',
                i18n_title_key: 'chat.messageFailed.title',
                i18n_message_key: 'notifications.messageDeadLettered',
                i18n_params: { channel: 'telegram', reason: 'timeout' },
              },
            },
          ],
          total: 1,
          unread_count: 1,
        });
      }
      return Promise.resolve({});
    });

    render(<NotificationBell />);
    await waitFor(() => expect(apiRequestMock).toHaveBeenCalledWith('/notifications?limit=20'));
    fireEvent.click(screen.getByRole('button', { name: 'title' }));

    // The stub translator returns the key, proving the stored keys drive the copy.
    await waitFor(() => expect(screen.getByText('chat.messageFailed.title')).toBeInTheDocument());
    expect(screen.getByText('notifications.messageDeadLettered')).toBeInTheDocument();
    expect(screen.queryByText('Message delivery failed')).not.toBeInTheDocument();
  });

  it('falls back to stored text when no catalog keys are present', async () => {
    apiRequestMock.mockImplementation((path: string) => {
      if (path === '/notifications?limit=20') {
        return Promise.resolve({
          items: [
            {
              id: 'notif-3',
              title: 'Legacy title',
              message: 'Legacy body',
              type: 'info',
              source: 'legacy',
              is_read: true,
              created_at: '2026-10-18T00:00:00Z',
              meta_data: null,
            },
          ],
          total: 1,
          unread_count: 0,
        });
      }
      return Promise.resolve({});
    });

    render(<NotificationBell />);
    await waitFor(() => expect(apiRequestMock).toHaveBeenCalledWith('/notifications?limit=20'));
    fireEvent.click(screen.getByRole('button', { name: 'title' }));

    await waitFor(() => expect(screen.getByText('Legacy title')).toBeInTheDocument());
    expect(screen.getByText('Legacy body')).toBeInTheDocument();
  });
});
