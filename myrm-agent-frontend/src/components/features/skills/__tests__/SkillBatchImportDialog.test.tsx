/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SkillBatchImportDialog from '../SkillBatchImportDialog';

const toastMock = vi.hoisted(() => vi.fn());

const TRANSLATIONS: Record<string, string> = {
  'upload.singleArchiveOnly': 'singleArchiveOnly',
  'upload.archiveOnly': 'archiveOnly',
  'discover.previewFailed': 'previewFailed',
  'installed.importFailed': 'importFailed',
  'batchImport.errors.archiveSecurity.executableBinaryDetected': 'Blocked: executable binary',
  'batchImport.errors.archiveSecurity.totalSizeExceeded': 'Blocked: total size exceeded',
};

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => TRANSLATIONS[key] ?? key,
}));

vi.mock('@/hooks/useToast', () => ({
  toast: toastMock,
}));

function mockResponse(ok: boolean, payload: unknown): Response {
  return {
    ok,
    json: async () => payload,
  } as Response;
}

function uploadZip(input: HTMLInputElement): void {
  const zipFile = new File(['zip-bytes'], 'skills.zip', { type: 'application/zip' });
  fireEvent.change(input, { target: { files: [zipFile] } });
}

describe('SkillBatchImportDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn() as unknown as typeof fetch;
  });

  it('shows mapped archive_security preview message from error_code', async () => {
    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      mockResponse(false, {
        detail: {
          message: 'Raw preview error',
          error_code: 'archive_security.executable_binary_detected',
        },
      }),
    );

    render(<SkillBatchImportDialog open={true} onOpenChange={vi.fn()} onImportComplete={vi.fn()} />);

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement | null;
    expect(fileInput).not.toBeNull();
    uploadZip(fileInput as HTMLInputElement);

    await waitFor(() => {
      expect(screen.getByText('Blocked: executable binary')).toBeInTheDocument();
    });
  });

  it('uses mapped archive_security message in confirm-import failure toast', async () => {
    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce(
        mockResponse(true, {
          total_found: 1,
          total_conflicts: 0,
          session_id: 'session-1',
          items: [
            {
              virtual_id: 'v1',
              name: 'skill-one',
              description: 'demo',
              conflict_type: 'none',
              existing_skill_id: null,
              security_issues: null,
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockResponse(false, {
          detail: {
            message: 'Raw import error',
            error_code: 'archive_security.total_size_exceeded',
          },
        }),
      );

    render(<SkillBatchImportDialog open={true} onOpenChange={vi.fn()} onImportComplete={vi.fn()} />);

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement | null;
    expect(fileInput).not.toBeNull();
    uploadZip(fileInput as HTMLInputElement);

    await waitFor(() => {
      expect(screen.getByText('skill-one')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /确认导入/ }));

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({
          title: '导入失败 / Import Failed',
          description: 'Blocked: total size exceeded',
          variant: 'destructive',
        }),
      );
    });
  });
});
