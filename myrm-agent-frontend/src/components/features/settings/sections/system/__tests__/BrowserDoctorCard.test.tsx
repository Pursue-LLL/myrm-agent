/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const apiRequestMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: apiRequestMock,
}));

import { ApiError } from '@/lib/api';
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
  apiRequestMock.mockReset();
  apiRequestMock.mockResolvedValue({ killed: 0, dry_run: true });
  vi.stubGlobal('fetch', fetchMock);
});

describe('BrowserDoctorCard', () => {
  it('renders a cleanup button when orphan processes are detected', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(doctorReport('warning'))));

    render(<BrowserDoctorCard />);

    expect(await screen.findByText('cleanupOrphans')).toBeInTheDocument();
  });

  it('hides the cleanup button when there are no orphan processes', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(doctorReport('ok'))));

    render(<BrowserDoctorCard />);

    await screen.findByText('checkNames.patchright');
    expect(screen.queryByText('cleanupOrphans')).not.toBeInTheDocument();
  });

  it('confirms cleanup, calls DELETE endpoint and refreshes the report', async () => {
    apiRequestMock.mockResolvedValue({ killed: 2, dry_run: false });
    let doctorCalls = 0;
    fetchMock.mockImplementation(() => {
      doctorCalls += 1;
      return Promise.resolve(jsonResponse(doctorReport(doctorCalls === 1 ? 'warning' : 'ok')));
    });

    render(<BrowserDoctorCard />);

    await screen.findByText('cleanupOrphans');
    await userEvent.click(screen.getByText('cleanupOrphans'));

    // Dialog opens with a confirm action inside the alertdialog container.
    const dialog = await screen.findByRole('alertdialog');
    const confirmBtn = within(dialog).getByRole('button', { name: 'cleanupOrphans' });
    await userEvent.click(confirmBtn);

    await vi.waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledTimes(1);
    });
    expect(apiRequestMock).toHaveBeenCalledWith('/health/browser/orphans?confirm=true', {
      method: 'DELETE',
      silent: true,
    });

    // After cleanup the report refreshes: the button disappears and the result is shown.
    await vi.waitFor(() => {
      expect(screen.queryByText('cleanupOrphans')).not.toBeInTheDocument();
    });
    expect(screen.getByText('cleaned')).toBeInTheDocument();
  });

  it('shows a partial-failure message when some processes could not be killed', async () => {
    apiRequestMock.mockResolvedValue({
      killed: 1,
      dry_run: false,
      failed: [{ pid: 4242, reason: 'permission_denied' }],
    });
    let doctorCalls = 0;
    fetchMock.mockImplementation(() => {
      doctorCalls += 1;
      return Promise.resolve(jsonResponse(doctorReport(doctorCalls === 1 ? 'warning' : 'ok')));
    });

    render(<BrowserDoctorCard />);

    await screen.findByText('cleanupOrphans');
    await userEvent.click(screen.getByText('cleanupOrphans'));

    const dialog = await screen.findByRole('alertdialog');
    const confirmBtn = within(dialog).getByRole('button', { name: 'cleanupOrphans' });
    await userEvent.click(confirmBtn);

    await vi.waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledTimes(1);
    });
    await vi.waitFor(() => {
      expect(screen.queryByText('cleanupOrphans')).not.toBeInTheDocument();
    });
    expect(screen.getByText('cleanupPartial')).toBeInTheDocument();
  });

  it('clears the previous cleanup message when running a fresh diagnosis', async () => {
    let doctorCalls = 0;
    fetchMock.mockImplementation(() => {
      doctorCalls += 1;
      const orphanStatus = doctorCalls === 1 ? 'warning' : 'ok';
      return Promise.resolve(jsonResponse(doctorReport(orphanStatus)));
    });
    apiRequestMock.mockResolvedValue({ killed: 2, dry_run: false, failed: [] });

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
    apiRequestMock
      .mockResolvedValueOnce({ killed: 2, dry_run: false, failed: [] })
      .mockRejectedValueOnce(new ApiError('Failed to process orphans', 500));
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(doctorReport('warning'))));

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
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(doctorReport('warning'))));
    apiRequestMock.mockRejectedValue(new ApiError('Failed to process orphans', 500));

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
        jsonResponse({ success: false, code: 500, message: 'Internal server error', error: null }, false),
      ),
    );

    render(<BrowserDoctorCard />);

    expect(await screen.findByText('Internal server error')).toBeInTheDocument();
  });

  it('extracts the first issue message from a FastAPI validation array', async () => {
    fetchMock.mockImplementation((_url: string) =>
      Promise.resolve(
        jsonResponse({ detail: [{ loc: ['query', 'launch_test'], msg: 'Input should be a valid boolean' }] }, false),
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

describe('BrowserDoctorCard presentation', () => {
  const RAW_CAMOUFOX = 'camoufox not ready: package is not installed (stealth auto-upgrade unavailable)';
  const RAW_LAUNCH = 'Browser launch failed: executable missing';

  function serveReport(report: unknown): void {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(report)));
  }

  function optionalOnlyReport() {
    return {
      summary: '2/3 checks passed, 1 warnings',
      overall_healthy: true,
      checks: {
        patchright: { status: 'ok', message: 'patchright 1.63.0 installed' },
        camoufox: { status: 'warning', message: RAW_CAMOUFOX, fix: 'uv add camoufox', details: { optional: true } },
      },
      recommendations: [],
    };
  }

  function failedLaunchReport() {
    return {
      summary: '1/2 checks passed, 1 errors',
      overall_healthy: false,
      checks: {
        patchright: { status: 'ok', message: 'patchright 1.63.0 installed' },
        browser_launch: { status: 'error', message: RAW_LAUNCH, fix: 'patchright install chromium' },
      },
      recommendations: ['patchright install chromium'],
    };
  }

  it('summarizes optional warnings as a calm, localized state and keeps raw diagnostics hidden', async () => {
    serveReport(optionalOnlyReport());

    render(<BrowserDoctorCard />);

    expect(await screen.findByText('summaryAllClear')).toBeInTheDocument();
    expect(screen.getByText('summaryOptional')).toBeInTheDocument();
    expect(screen.getByText('healthy')).toBeInTheDocument();
    expect(screen.getByText('optionalCamoufox')).toBeInTheDocument();
    expect(screen.getByText('statusOptional')).toBeInTheDocument();
    expect(screen.queryByText('summaryNeedsAttention')).not.toBeInTheDocument();
    expect(screen.queryByText(RAW_CAMOUFOX)).not.toBeInTheDocument();
    expect(screen.queryByText('2/3 checks passed, 1 warnings')).not.toBeInTheDocument();
  });

  it('reveals the raw English message and fix only after opening technical details', async () => {
    serveReport(optionalOnlyReport());

    render(<BrowserDoctorCard />);

    const toggle = await screen.findByRole('button', { name: 'technicalDetails' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(RAW_CAMOUFOX)).toBeInTheDocument();
    expect(screen.getByText('fix: uv add camoufox')).toBeInTheDocument();

    await userEvent.click(toggle);

    expect(screen.queryByText(RAW_CAMOUFOX)).not.toBeInTheDocument();
  });

  it('opens technical details by default when something failed and lets the user collapse them', async () => {
    serveReport(failedLaunchReport());

    render(<BrowserDoctorCard />);

    expect(await screen.findByText('summaryNeedsAttention')).toBeInTheDocument();
    expect(screen.getByText('unhealthy')).toBeInTheDocument();
    expect(screen.getByText('errorGeneric')).toBeInTheDocument();
    expect(screen.getByText(RAW_LAUNCH)).toBeInTheDocument();
    expect(screen.getByRole('list')).toHaveTextContent('patchright install chromium');

    await userEvent.click(screen.getByRole('button', { name: 'technicalDetails' }));

    expect(screen.queryByText(RAW_LAUNCH)).not.toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('lists the checks directly in the card instead of inside a second scroll area', async () => {
    serveReport(failedLaunchReport());

    const { container } = render(<BrowserDoctorCard />);

    await screen.findByText('summaryNeedsAttention');
    expect(container.querySelector('[class*="overflow-y-auto"]')).toBeNull();
  });

  it('announces a failed diagnosis to assistive technology', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ detail: 'Doctor backend exploded' }, false)));

    render(<BrowserDoctorCard />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Doctor backend exploded');
  });

  it('announces the cleanup result in a polite live region that exists before the result arrives', async () => {
    let doctorCalls = 0;
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/browser/doctor')) {
        doctorCalls += 1;
        return Promise.resolve(jsonResponse(doctorReport(doctorCalls === 1 ? 'warning' : 'ok')));
      }
      return Promise.resolve(jsonResponse({ killed: 2, dry_run: false }));
    });

    render(<BrowserDoctorCard />);

    await screen.findByText('cleanupOrphans');
    const liveRegion = screen.getByRole('status');
    expect(liveRegion).toBeEmptyDOMElement();

    await userEvent.click(screen.getByText('cleanupOrphans'));
    const dialog = await screen.findByRole('alertdialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'cleanupOrphans' }));

    await vi.waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('cleaned');
    });
    expect(screen.getByRole('status')).toBe(liveRegion);
  });

  it('does not report a healthy stack when a real warning exists even if the backend verdict is healthy', async () => {
    serveReport({
      summary: '1/2 checks passed, 1 warnings',
      overall_healthy: true,
      checks: { disk: { status: 'warning', message: 'Disk space tight', details: { available_gb: 0.8 } } },
      recommendations: [],
    });

    render(<BrowserDoctorCard />);

    expect(await screen.findByText('summaryNeedsAttention')).toBeInTheDocument();
    expect(screen.getByText('unhealthy')).toBeInTheDocument();
    expect(screen.getByText('diskLow')).toBeInTheDocument();
  });
});
