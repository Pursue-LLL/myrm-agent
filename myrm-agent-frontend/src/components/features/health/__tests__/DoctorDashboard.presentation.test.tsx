/** @vitest-environment jsdom */
'use client';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../../locales/en.json';
import zh from '../../../../../locales/zh.json';
import { DoctorDashboard } from '../DoctorDashboard';
import type { DoctorResponse } from '@/services/runtime-health';

const mockGetRuntimeDoctor = vi.fn<() => Promise<DoctorResponse>>();

// What the user reads is the behaviour under test, so the real next-intl runs instead of the global mock.
vi.mock('next-intl', async (importOriginal) => await importOriginal());

vi.mock('sonner', () => ({
  toast: { error: vi.fn() },
}));

vi.mock('@/services/runtime-health', () => ({
  getRuntimeDoctor: () => mockGetRuntimeDoctor(),
}));

vi.mock('@/lib/utils/diagnostic-export', () => ({
  copyDiagnosticMarkdown: vi.fn(async () => true),
  downloadDiagnosticJson: vi.fn(),
}));

vi.mock('../GuidedRepairCard', () => ({
  GuidedRepairCard: () => null,
}));

vi.mock('@tauri-apps/plugin-shell', () => ({
  open: vi.fn(() => Promise.reject(new Error('not tauri'))),
}));

const HOOK_FUNCTION_NAME = 'check_network_health';
const SWAP_MESSAGE = 'Swap/Pagefile usage is high.';
const SWAP_MEASURED = 'Swap 93.6%';
const PASS_MESSAGE = 'Database is healthy.';

const doctorResponse: DoctorResponse = {
  harness: [
    {
      component_name: HOOK_FUNCTION_NAME,
      status: 'fail',
      message: 'A system check did not finish in time.',
      detail: 'Diagnostic timed out (>5.0s); the check may be blocked or the machine may be busy.',
      fix_suggestion: 'Run the check again in a moment.',
    },
    {
      component_name: 'SystemExhaustion',
      status: 'warn',
      message: SWAP_MESSAGE,
      detail: 'Swap/Pagefile: 93.6% (24914.9/26624.0MB), Available memory: 26.0%',
      measured: SWAP_MEASURED,
      expected: 'Swap <70%',
      cause: 'Idle pages were moved to swap earlier.',
      fix_suggestion: 'Inspect orphan worker processes consuming virtual memory.',
    },
    { component_name: 'Database', status: 'pass', message: PASS_MESSAGE },
  ],
  server: [],
  repair_actions: [],
};

type Messages = typeof en;

const renderDoctor = (locale: string, messages: Messages) => {
  const intlErrors: string[] = [];
  render(
    <NextIntlClientProvider locale={locale} messages={messages} onError={(error) => intlErrors.push(error.code)}>
      <DoctorDashboard />
    </NextIntlClientProvider>,
  );
  return intlErrors;
};

describe.each([
  ['en', en],
  ['zh', zh],
])('DoctorDashboard rows in %s', (locale, messages) => {
  const doctor = messages.settings.systemHealth.doctor;

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetRuntimeDoctor.mockResolvedValue(doctorResponse);
  });

  it('shows localized titles, status labels and hints, and no English probe text or function name', async () => {
    const intlErrors = renderDoctor(locale, messages);

    expect(await screen.findByText(doctor.components.SystemExhaustion)).toBeInTheDocument();
    expect(screen.getByText(doctor.hints.SystemExhaustion.warn)).toBeInTheDocument();
    expect(screen.getByText(doctor.status.warn)).toBeInTheDocument();
    expect(screen.getByText(doctor.status.fail)).toBeInTheDocument();
    expect(screen.getByText(doctor.components.generic)).toBeInTheDocument();
    expect(screen.getByText(doctor.hints.generic.fail)).toBeInTheDocument();
    expect(screen.getByText(doctor.components.Database)).toBeInTheDocument();
    // A passing report keeps the backend wording; everything else English is behind the technical details.
    expect(screen.getByText(PASS_MESSAGE)).toBeInTheDocument();
    expect(screen.queryByText(SWAP_MESSAGE)).not.toBeInTheDocument();
    expect(screen.queryByText(SWAP_MEASURED)).not.toBeInTheDocument();
    expect(screen.queryByText(HOOK_FUNCTION_NAME)).not.toBeInTheDocument();
    expect(intlErrors).toEqual([]);
  });

  it('reveals the English original, the measured values and the raw component name on demand', async () => {
    renderDoctor(locale, messages);
    await screen.findByText(doctor.components.SystemExhaustion);

    const toggle = screen.getByRole('button', { name: doctor.technical.toggle });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(SWAP_MESSAGE)).toBeInTheDocument();
    expect(screen.getByText(SWAP_MEASURED)).toBeInTheDocument();
    expect(screen.getByText(HOOK_FUNCTION_NAME)).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText(SWAP_MESSAGE)).not.toBeInTheDocument();
  });

  it.each([
    ['the localized title', doctor.components.SystemExhaustion],
    ['the English original message', 'swap/pagefile usage'],
    ['the raw component name', 'systemexhaustion'],
  ])('finds a row by %s', async (_label, query) => {
    renderDoctor(locale, messages);
    await screen.findByText(doctor.components.SystemExhaustion);

    fireEvent.change(screen.getByPlaceholderText(doctor.searchPlaceholder), { target: { value: query } });

    await waitFor(() => {
      expect(screen.queryByText(doctor.components.Database)).not.toBeInTheDocument();
    });
    expect(screen.getByText(doctor.components.SystemExhaustion)).toBeInTheDocument();
  });

  it('shows the empty state when no row matches', async () => {
    renderDoctor(locale, messages);
    await screen.findByText(doctor.components.SystemExhaustion);

    fireEvent.change(screen.getByPlaceholderText(doctor.searchPlaceholder), { target: { value: 'no-such-probe' } });

    expect(await screen.findByText(doctor.noProbes)).toBeInTheDocument();
  });
});
