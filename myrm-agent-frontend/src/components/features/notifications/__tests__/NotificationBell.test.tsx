/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockPush = vi.fn();
const apiRequestMock = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
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
});
