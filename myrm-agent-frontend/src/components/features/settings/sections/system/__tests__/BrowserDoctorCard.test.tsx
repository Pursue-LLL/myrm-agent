/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

import BrowserDoctorCard from '../BrowserDoctorCard';

interface DoctorCheck {
  status: string;
  message: string;
  details?: Record<string, unknown>;
}

function doctorReport(orphanStatus: string): {
  summary: string;
  overall_healthy: boolean;
  checks: Record<string, DoctorCheck>;
  recommendations: string[];
} {
  return {
    summary: '5/6 checks passed, 1 warnings',
    overall_healthy: orphanStatus === 'ok',
    checks: {
      patchright: { status: 'ok', message: 'patchright installed' },
      orphan_processes: {
        status: orphanStatus,
        message: orphanStatus === 'ok' ? 'No orphan processes' : 'Found 2 orphan processes',
        details: { count: orphanStatus === 'ok' ? 0 : 2 },
      },
    },
    recommendations: [],
  };
}

function jsonResponse(data: unknown, ok = true): Response {
  return {
    ok,
    status: ok ? 200 : 500,
    json: async () => data,
    text: async () => JSON.stringify(data),
  } as unknown as Response;
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

describe('BrowserDoctorCard', () => {
  it('renders a cleanup button when orphan processes are detected', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/browser/doctor')) {
        return Promise.resolve(jsonResponse(doctorReport('warning')));
      }
      return Promise.resolve(jsonResponse({ killed: 0, dry_run: true }));
    });

    render(<BrowserDoctorCard />);

    expect(await screen.findByText('cleanupOrphans')).toBeInTheDocument();
  });

  it('hides the cleanup button when there are no orphan processes', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/browser/doctor')) {
        return Promise.resolve(jsonResponse(doctorReport('ok')));
      }
      return Promise.resolve(jsonResponse({ killed: 0, dry_run: true }));
    });

    render(<BrowserDoctorCard />);

    await screen.findByText('checkNames.patchright');
    expect(screen.queryByText('cleanupOrphans')).not.toBeInTheDocument();
  });

  it('confirms cleanup, calls DELETE endpoint and refreshes the report', async () => {
    const deleteMock = vi.fn(() => Promise.resolve(jsonResponse({ killed: 2, dry_run: false })));
    let doctorCalls = 0;
    const doctorMock = vi.fn((url: string) => {
      if (url.includes('/browser/doctor')) {
        doctorCalls += 1;
        return Promise.resolve(jsonResponse(doctorReport(doctorCalls === 1 ? 'warning' : 'ok')));
      }
      return deleteMock();
    });
    fetchMock.mockImplementation(doctorMock);

    render(<BrowserDoctorCard />);

    await screen.findByText('cleanupOrphans');
    await userEvent.click(screen.getByText('cleanupOrphans'));

    // Dialog opens with a confirm action inside the alertdialog container.
    const dialog = await screen.findByRole('alertdialog');
    const confirmBtn = within(dialog).getByRole('button', { name: 'cleanupOrphans' });
    await userEvent.click(confirmBtn);

    await vi.waitFor(() => {
      expect(deleteMock).toHaveBeenCalledTimes(1);
    });
    const deleteCall = deleteMock.mock.calls[0];
    expect(deleteCall).toBeDefined();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/browser/orphans'))).toHaveLength(1);

    // After cleanup the report refreshes: the button disappears and the result is shown.
    await vi.waitFor(() => {
      expect(screen.queryByText('cleanupOrphans')).not.toBeInTheDocument();
    });
    expect(screen.getByText('cleaned')).toBeInTheDocument();
  });
});
