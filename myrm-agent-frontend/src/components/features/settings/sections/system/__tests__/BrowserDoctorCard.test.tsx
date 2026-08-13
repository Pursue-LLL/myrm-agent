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

  it('shows a partial-failure message when some processes could not be killed', async () => {
    const deleteMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          killed: 1,
          dry_run: false,
          failed: [{ pid: 4242, reason: 'permission_denied' }],
        }),
      ),
    );
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

    const dialog = await screen.findByRole('alertdialog');
    const confirmBtn = within(dialog).getByRole('button', { name: 'cleanupOrphans' });
    await userEvent.click(confirmBtn);

    await vi.waitFor(() => {
      expect(deleteMock).toHaveBeenCalledTimes(1);
    });
    await vi.waitFor(() => {
      expect(screen.queryByText('cleanupOrphans')).not.toBeInTheDocument();
    });
    expect(screen.getByText('cleanupPartial')).toBeInTheDocument();
  });

  it('clears the previous cleanup message when running a fresh diagnosis', async () => {
    let doctorCalls = 0;
    const doctorMock = vi.fn((_url: string) => {
      doctorCalls += 1;
      const orphanStatus = doctorCalls === 1 ? 'warning' : 'ok';
      return Promise.resolve(jsonResponse(doctorReport(orphanStatus)));
    });
    const deleteMock = vi.fn(() =>
      Promise.resolve(jsonResponse({ killed: 2, dry_run: false, failed: [] })),
    );
    fetchMock.mockImplementation((_url: string) =>
      String(_url).includes('/browser/doctor') ? doctorMock(_url) : deleteMock(),
    );

    render(<BrowserDoctorCard />);

    await screen.findByText('cleanupOrphans');
    await userEvent.click(screen.getByText('cleanupOrphans'));

    const dialog = await screen.findByRole('alertdialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'cleanupOrphans' }));

    await vi.waitFor(() => {
      expect(screen.getByText('cleaned')).toBeInTheDocument();
    });

    // Re-running the diagnosis drops the stale cleanup feedback.
    await userEvent.click(screen.getByText('runCheck'));
    await vi.waitFor(() => {
      expect(screen.queryByText('cleaned')).not.toBeInTheDocument();
    });
  });

  it('drops a previous success message when a later cleanup fails', async () => {
    let deleteCalls = 0;
    const deleteMock = vi.fn(() => {
      deleteCalls += 1;
      if (deleteCalls === 1) {
        return Promise.resolve(jsonResponse({ killed: 2, dry_run: false, failed: [] }));
      }
      return Promise.resolve(jsonResponse({ detail: 'Failed to process orphans' }, false));
    });
    const doctorMock = vi.fn((url: string) => {
      if (url.includes('/browser/doctor')) {
        return Promise.resolve(jsonResponse(doctorReport('warning')));
      }
      return deleteMock();
    });
    fetchMock.mockImplementation(doctorMock);

    render(<BrowserDoctorCard />);

    // First cleanup succeeds and shows the success message.
    await screen.findByText('cleanupOrphans');
    await userEvent.click(screen.getByText('cleanupOrphans'));
    let dialog = await screen.findByRole('alertdialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'cleanupOrphans' }));
    await vi.waitFor(() => {
      expect(screen.getByText('cleaned')).toBeInTheDocument();
    });

    // Second cleanup fails: the stale success message must be gone.
    await userEvent.click(screen.getByText('cleanupOrphans'));
    dialog = await screen.findByRole('alertdialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'cleanupOrphans' }));

    await vi.waitFor(() => {
      expect(screen.getByText('Failed to process orphans')).toBeInTheDocument();
    });
    expect(screen.queryByText('cleaned')).not.toBeInTheDocument();
  });

  it('shows the server error detail instead of a raw JSON string when the doctor request fails', async () => {
    fetchMock.mockImplementation((_url: string) =>
      Promise.resolve(jsonResponse({ detail: 'Doctor backend exploded' }, false)),
    );

    render(<BrowserDoctorCard />);

    const message = await screen.findByText('Doctor backend exploded');
    expect(message.textContent).toBe('Doctor backend exploded');
  });

  it('shows the server error detail instead of a raw JSON string when cleanup fails', async () => {
    const doctorMock = vi.fn((_url: string) =>
      Promise.resolve(jsonResponse(doctorReport('warning'))),
    );
    const deleteMock = vi.fn(() =>
      Promise.resolve(jsonResponse({ detail: 'Failed to process orphans' }, false)),
    );
    fetchMock.mockImplementation((_url: string) =>
      String(_url).includes('/browser/doctor') ? doctorMock(_url) : deleteMock(),
    );

    render(<BrowserDoctorCard />);

    await screen.findByText('cleanupOrphans');
    await userEvent.click(screen.getByText('cleanupOrphans'));

    const dialog = await screen.findByRole('alertdialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'cleanupOrphans' }));

    expect(await screen.findByText('Failed to process orphans')).toBeInTheDocument();
  });

  it('shows a non-JSON error body verbatim', async () => {
    fetchMock.mockImplementation((_url: string) =>
      Promise.resolve({
        ok: false,
        status: 500,
        json: async () => undefined,
        text: async () => 'Internal Server Error',
      } as unknown as Response),
    );

    render(<BrowserDoctorCard />);

    expect(await screen.findByText('Internal Server Error')).toBeInTheDocument();
  });

  it('shows the server message field instead of the raw JSON envelope', async () => {
    fetchMock.mockImplementation((_url: string) =>
      Promise.resolve(
        jsonResponse(
          { success: false, code: 500, message: 'Internal server error', error: null },
          false,
        ),
      ),
    );

    render(<BrowserDoctorCard />);

    expect(await screen.findByText('Internal server error')).toBeInTheDocument();
  });

  it('extracts the first issue message from a FastAPI validation array', async () => {
    fetchMock.mockImplementation((_url: string) =>
      Promise.resolve(
        jsonResponse(
          { detail: [{ loc: ['query', 'launch_test'], msg: 'Input should be a valid boolean' }] },
          false,
        ),
      ),
    );

    render(<BrowserDoctorCard />);

    expect(await screen.findByText('Input should be a valid boolean')).toBeInTheDocument();
  });

  it('falls back to the localized message when the error body is empty', async () => {
    fetchMock.mockImplementation((_url: string) =>
      Promise.resolve({
        ok: false,
        status: 500,
        json: async () => undefined,
        text: async () => '',
      } as unknown as Response),
    );

    render(<BrowserDoctorCard />);

    expect(await screen.findByText('loadFailed')).toBeInTheDocument();
  });
});
