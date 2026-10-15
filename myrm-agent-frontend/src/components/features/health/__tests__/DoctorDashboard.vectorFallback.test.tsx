/** @vitest-environment jsdom */
'use client';

import { render, screen, waitFor } from '@testing-library/react';
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

const mockGetRuntimeDoctor = vi.fn<() => Promise<DoctorResponse>>();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

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

const memoryFallbackDoctor: DoctorResponse = {
  harness: [
    {
      component_name: 'VectorDB',
      status: 'fail',
      code: MEMORY_FALLBACK_CODE,
      message: 'New memories are not being saved permanently.',
      detail: 'The memory data folder could not be opened.',
      fix_suggestion: 'Quit any other running copy of the app, then restart the app.',
    },
  ],
  server: [],
  repair_actions: [],
};

describe('DoctorDashboard memory fallback verdict', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetRuntimeDoctor.mockResolvedValue(memoryFallbackDoctor);
  });

  it('asks the locale files for the verdict through its code', async () => {
    render(<DoctorDashboard />);

    await waitFor(() => {
      expect(screen.getByText(`errors.${MEMORY_FALLBACK_CODE}.message`)).toBeInTheDocument();
    });
    expect(screen.getByText('FAIL')).toBeInTheDocument();
  });

  it.each([
    ['de', de],
    ['en', en],
    ['ja', ja],
    ['ko', ko],
    ['zh', zh],
    ['zh-TW', zhTW],
  ])('%s translates the verdict under settings.systemHealth.doctor.errors', (_locale, messages) => {
    expect(messages.settings.systemHealth.doctor.errors.ERR_VECTOR_STORE_ON_MEMORY_FALLBACK.message).not.toBe('');
  });
});
