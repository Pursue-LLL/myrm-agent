/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const configStore = vi.hoisted(() => ({ records: {} as Record<string, unknown> }));
vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({
    get: (key: string) => configStore.records[key],
    set: vi.fn(),
  }),
}));

const apiRequestMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: apiRequestMock,
}));

import { ApiError } from '@/lib/api';
import BrowserProxyCard from '../BrowserProxyCard';
import CloudBrowserCard from '../CloudBrowserCard';

beforeEach(() => {
  apiRequestMock.mockReset();
  configStore.records = {
    browserCloudProvider: { enabled: true, provider: 'browserbase', credential: 'secret', custom_ws_url: '' },
    browserProxy: { enabled: true, proxies: ['http://127.0.0.1:8080'] },
  };
});

describe.each([
  ['CloudBrowserCard', CloudBrowserCard, '/health/browser/test-cloud-connection'],
  ['BrowserProxyCard', BrowserProxyCard, '/health/browser/test-proxy-connection'],
])('%s connection test', (_name, Card, endpoint) => {
  it('posts through the authenticated API client and shows the result', async () => {
    apiRequestMock.mockResolvedValue({ status: 'connected', message: 'Connected in 42ms' });
    render(<Card />);

    await userEvent.click(screen.getByRole('button', { name: 'testConnection' }));

    expect(apiRequestMock).toHaveBeenCalledWith(endpoint, { method: 'POST', silent: true });
    expect(await screen.findByText('Connected in 42ms')).toBeInTheDocument();
  });

  it('shows the failure reported by the server body', async () => {
    apiRequestMock.mockResolvedValue({ status: 'failed', error: 'Handshake refused' });
    render(<Card />);

    await userEvent.click(screen.getByRole('button', { name: 'testConnection' }));

    expect(await screen.findByText('Handshake refused')).toBeInTheDocument();
  });

  it('shows the error message when the request itself is rejected', async () => {
    apiRequestMock.mockRejectedValue(new ApiError('Authentication required', 401));
    render(<Card />);

    await userEvent.click(screen.getByRole('button', { name: 'testConnection' }));

    expect(await screen.findByText('Authentication required')).toBeInTheDocument();
  });
});
