/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));

const apiRequestMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: apiRequestMock,
}));

import { ApiError } from '@/lib/api';
import MemoryMonitorCard from '../MemoryMonitorCard';

beforeEach(() => {
  apiRequestMock.mockReset();
  toastMock.success.mockReset();
  toastMock.error.mockReset();
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ history: [] }) } as unknown as Response)),
  );
});

describe('MemoryMonitorCard profiling controls', () => {
  it('starts profiling through the authenticated API client', async () => {
    apiRequestMock.mockResolvedValue({ status: 'started' });
    render(<MemoryMonitorCard />);

    await userEvent.click(screen.getByText('Start Heap Profiling'));

    expect(apiRequestMock).toHaveBeenCalledWith('/health/memory/profile/start', { method: 'POST', silent: true });
    expect(toastMock.success).toHaveBeenCalledWith('profilingStarted');
    expect(await screen.findByText('Stop Profiling')).toBeInTheDocument();
  });

  it('shows the server detail when starting is rejected and stays stopped', async () => {
    apiRequestMock.mockRejectedValue(new ApiError('Profiling is already running', 400));
    render(<MemoryMonitorCard />);

    await userEvent.click(screen.getByText('Start Heap Profiling'));

    expect(toastMock.error).toHaveBeenCalledWith('Profiling is already running');
    expect(screen.getByText('Start Heap Profiling')).toBeInTheDocument();
  });

  it('reports a transport failure with the localized network message', async () => {
    apiRequestMock.mockRejectedValue(new TypeError('Failed to fetch'));
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    render(<MemoryMonitorCard />);

    await userEvent.click(screen.getByText('Start Heap Profiling'));

    expect(toastMock.error).toHaveBeenCalledWith('profilingStartNetworkError');
  });

  it('stops profiling through the authenticated API client and keeps the allocations', async () => {
    apiRequestMock.mockResolvedValueOnce({ status: 'started' }).mockResolvedValueOnce({
      status: 'stopped',
      top_allocations: [{ file: 'a.py', line: 3, size_kb: 1536, count: 2 }],
    });
    render(<MemoryMonitorCard />);

    await userEvent.click(screen.getByText('Start Heap Profiling'));
    await userEvent.click(await screen.findByText('Stop Profiling'));

    expect(apiRequestMock).toHaveBeenLastCalledWith('/health/memory/profile/stop', { method: 'POST', silent: true });
    expect(toastMock.success).toHaveBeenLastCalledWith('profilingStopped');
    expect(await screen.findByText('Start Heap Profiling')).toBeInTheDocument();
    expect(screen.getByText('a.py')).toBeInTheDocument();
  });
});
