/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import type { ExportJob } from '@/services/instanceArchive';
import { ExportCard } from '../ExportCard';

const { service } = vi.hoisted(() => ({
  service: {
    startExport: vi.fn(),
    getExport: vi.fn(),
    discardExport: vi.fn(),
    downloadExport: vi.fn(),
  },
}));

vi.mock('@/services/instanceArchive', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/instanceArchive')>()),
  instanceArchiveService: service,
}));

const stableT = (key: string, params?: Record<string, unknown>) =>
  params ? `${key}:${Object.values(params).join('|')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const apiError = (code: string, status = 400) => new ApiError('server wording', status, [], undefined, code);

const doneJob = (overrides: Partial<ExportJob> = {}): ExportJob => ({
  job_id: 'job-1',
  state: 'done',
  files_done: 3,
  files_total: 3,
  bytes_done: 2048,
  bytes_total: 2048,
  size_bytes: 2048,
  error_code: null,
  reentry: [],
  config_key_carried: false,
  unreadable_count: 0,
  ...overrides,
});

beforeEach(() => {
  vi.clearAllMocks();
  service.discardExport.mockResolvedValue(undefined);
});

describe('ExportCard', () => {
  it('starts a key-free export by default and lists what is left out', async () => {
    service.startExport.mockResolvedValue(doneJob({ reentry: ['config:providers', 'table:vault_credentials'] }));

    render(<ExportCard canProtectSecrets />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));

    expect(await screen.findByText('notIncluded')).toBeInTheDocument();
    expect(service.startExport).toHaveBeenCalledWith(undefined);
    expect(screen.getByText('modelKeys')).toBeInTheDocument();
    expect(screen.getByText('savedSecrets')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'save' })).toBeInTheDocument();
  });

  it('says how many items could not be read and does not present that backup as a clean success', async () => {
    service.startExport.mockResolvedValueOnce(doneJob({ unreadable_count: 2 }));

    const { unmount } = render(<ExportCard canProtectSecrets />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    expect(await screen.findByText('unreadable:2')).toBeInTheDocument();
    expect(screen.getByText(/^ready:/).className).toContain('amber');
    unmount();

    service.startExport.mockResolvedValueOnce(doneJob());
    render(<ExportCard canProtectSecrets />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    expect(await screen.findByRole('button', { name: 'save' })).toBeInTheDocument();
    expect(screen.queryByText(/^unreadable/)).not.toBeInTheDocument();
    expect(screen.getByText(/^ready:/).className).toContain('emerald');
  });

  it('only sends a passphrase once it is long enough and repeated exactly', async () => {
    service.startExport.mockResolvedValue(doneJob({ config_key_carried: true }));

    render(<ExportCard canProtectSecrets />);
    fireEvent.click(screen.getByRole('switch'));
    const start = screen.getByRole('button', { name: 'start' });
    expect(start).toBeDisabled();

    fireEvent.change(screen.getByLabelText('passphrase'), { target: { value: 'short' } });
    expect(start).toBeDisabled();

    fireEvent.change(screen.getByLabelText('passphrase'), { target: { value: 'correct horse' } });
    fireEvent.change(screen.getByLabelText('passphraseRepeat'), { target: { value: 'correct hors' } });
    expect(start).toBeDisabled();
    expect(screen.getByText('passphraseMismatch')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('passphraseRepeat'), { target: { value: 'correct horse' } });
    expect(start).toBeEnabled();
    fireEvent.click(start);

    await waitFor(() => expect(service.startExport).toHaveBeenCalledWith('correct horse'));
    expect(await screen.findByText('keysSealed')).toBeInTheDocument();
  });

  it('states that keys stay out when this deployment cannot protect them', () => {
    render(<ExportCard canProtectSecrets={false} />);

    expect(screen.getByText('keysNotIncluded')).toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });

  it('shows localized copy for a refused export, never the server wording', async () => {
    service.startExport.mockRejectedValue(apiError('export_busy', 409));

    render(<ExportCard canProtectSecrets={false} />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));

    expect(await screen.findByText('export_busy')).toBeInTheDocument();
    expect(screen.queryByText('server wording')).not.toBeInTheDocument();
  });
});
