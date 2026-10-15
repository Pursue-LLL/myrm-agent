/** @vitest-environment jsdom */
'use client';

import { render, screen, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import de from '../../../../../locales/de.json';
import en from '../../../../../locales/en.json';
import ja from '../../../../../locales/ja.json';
import ko from '../../../../../locales/ko.json';
import zh from '../../../../../locales/zh.json';
import zhTW from '../../../../../locales/zh-TW.json';
import { DoctorDashboard } from '../DoctorDashboard';
import type { DoctorResponse } from '@/services/runtime-health';

const MEMORY_FALLBACK_CODE = 'ERR_VECTOR_STORE_ON_MEMORY_FALLBACK';
const CODE_WITHOUT_LOCALE_KEY = 'ERR_PROBE_CODE_WITHOUT_LOCALE_KEY';
const BACKEND_MESSAGE = 'Backend verdict for a code that has no locale entry.';

const mockGetRuntimeDoctor = vi.fn<() => Promise<DoctorResponse>>();

// The verdict lookup is the behaviour under test, so the real next-intl runs instead of the global mock.
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

const doctorResponse: DoctorResponse = {
  harness: [
    {
      component_name: 'VectorDB',
      status: 'fail',
      code: MEMORY_FALLBACK_CODE,
      message: 'New memories are not being saved permanently.',
    },
    {
      component_name: 'ProbeWithoutLocaleKey',
      status: 'warn',
      code: CODE_WITHOUT_LOCALE_KEY,
      message: BACKEND_MESSAGE,
    },
  ],
  server: [],
  repair_actions: [],
};

const renderDoctor = (locale: string, messages: typeof en) => {
  const intlErrors: string[] = [];
  render(
    <NextIntlClientProvider locale={locale} messages={messages} onError={(error) => intlErrors.push(error.code)}>
      <DoctorDashboard />
    </NextIntlClientProvider>,
  );
  return intlErrors;
};

describe('DoctorDashboard verdict localization', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetRuntimeDoctor.mockResolvedValue(doctorResponse);
  });

  it.each([
    ['en', en],
    ['zh', zh],
  ])(
    '%s shows the locale text for a code that has one and the backend message for one that has not',
    async (locale, messages) => {
      const intlErrors = renderDoctor(locale, messages);

      const localized = messages.settings.systemHealth.doctor.errors.ERR_VECTOR_STORE_ON_MEMORY_FALLBACK.message;
      await waitFor(() => {
        expect(screen.getByText(localized)).toBeInTheDocument();
      });
      expect(screen.getByText(BACKEND_MESSAGE)).toBeInTheDocument();
      expect(screen.queryByText(/settings\.systemHealth\.doctor\.errors/)).not.toBeInTheDocument();
      expect(intlErrors).toEqual([]);
    },
  );

  it.each([
    ['de', de],
    ['en', en],
    ['ja', ja],
    ['ko', ko],
    ['zh', zh],
    ['zh-TW', zhTW],
  ])('%s translates the memory fallback verdict', (_locale, messages) => {
    expect(messages.settings.systemHealth.doctor.errors.ERR_VECTOR_STORE_ON_MEMORY_FALLBACK.message).not.toBe('');
  });
});
