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
  'batchImport.importSuccess': 'Import Success',
  'batchImport.importSuccessDesc': 'Imported {imported}, skipped {skipped}, restored {restored}',
  'batchImport.importFailed': 'Import Failed',
  'batchImport.errors.archiveSecurity.executableBinaryDetected': 'Blocked: executable binary',
  'batchImport.errors.archiveSecurity.totalSizeExceeded': 'Blocked: total size exceeded',
  'batchImportDialog.confirmImport': 'Confirm Import',
  'confirmImport': 'Confirm Import',
};

const stableT = (key: string, values?: Record<string, string>): string => {
  const template = TRANSLATIONS[key] ?? key;
  if (!values) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (_, name: string) => values[name] ?? `{${name}}`);
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
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

    fireEvent.click(screen.getByRole('button', { name: /Confirm Import/ }));

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Import Failed',
          description: 'Blocked: total size exceeded',
          variant: 'destructive',
        }),
      );
    });
  });

  it('shows success toast with restored eval case count', async () => {
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
        mockResponse(true, {
          imported_count: 1,
          skipped_count: 0,
          restored_eval_cases: 2,
        }),
      );

    const onImportComplete = vi.fn();
    render(
      <SkillBatchImportDialog
        open={true}
        onOpenChange={vi.fn()}
        onImportComplete={onImportComplete}
      />,
    );

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement | null;
    expect(fileInput).not.toBeNull();
    uploadZip(fileInput as HTMLInputElement);

    await waitFor(() => {
      expect(screen.getByText('skill-one')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Confirm Import/ }));

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Import Success',
          description: 'Imported 1, skipped 0, restored 2',
        }),
      );
    });
    expect(onImportComplete).toHaveBeenCalled();
  });
});
