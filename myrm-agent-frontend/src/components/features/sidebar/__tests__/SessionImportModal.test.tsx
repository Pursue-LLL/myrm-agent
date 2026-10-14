// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import SessionImportModal from '../SessionImportModal';
import { importTranscriptJson } from '@/services/sessionImport';

// 带参数回显：同时验证翻译键与插值参数
const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('@/services/sessionImport', () => ({
  importTranscriptFile: vi.fn(),
  importTranscriptJson: vi.fn(),
}));

const renderModal = () => render(<SessionImportModal open={true} onOpenChange={vi.fn()} />);

describe('SessionImportModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the upload view through translation keys', () => {
    renderModal();

    for (const key of [
      'chat.import.modalTitle',
      'chat.import.modalSubtitle',
      'chat.import.cleanRecordBadge',
      'chat.import.tabUpload',
      'chat.import.tabPaste',
      'chat.import.dropHint',
      'chat.import.formatHint',
      'chat.import.featuresSummary',
      'common.cancel',
      'chat.import.startImport',
    ]) {
      expect(screen.getByText(key)).toBeDefined();
    }
  });

  it('rejects a dropped file that is not a json transcript with the translated message', () => {
    renderModal();

    const dropZone = screen.getByText('chat.import.dropHint').closest('button') as HTMLElement;
    const file = new File(['x'], 'notes.txt', { type: 'text/plain' });
    fireEvent.drop(dropZone, { dataTransfer: { files: [file] } });

    expect(toast.error).toHaveBeenCalledWith('chat.import.invalidFileType');
  });

  it('shows the import result with translated labels after pasting a transcript', async () => {
    vi.mocked(importTranscriptJson).mockResolvedValue({
      ok: true,
      chat_id: 'chat-1',
      title: 'Imported chat',
      source_platform: 'codex',
      turns_count: 7,
      raw_tokens_estimate: 1000,
      clean_tokens_estimate: 580,
      reduction_ratio: 0.42,
    });
    renderModal();

    fireEvent.click(screen.getByTestId('import-tab-paste'));
    fireEvent.change(screen.getByTestId('import-paste-textarea'), { target: { value: '{"a":1}' } });
    fireEvent.click(screen.getByTestId('import-submit-btn'));

    await waitFor(() => expect(screen.getByTestId('import-result-stats')).toBeDefined());
    expect(toast.success).toHaveBeenCalledWith('chat.import.successToast:{"count":7}');
    expect(screen.getByText('chat.import.successTitle')).toBeDefined();
    expect(screen.getByText('42%')).toBeDefined();
    expect(screen.getByText('chat.import.resumeNow')).toBeDefined();
  });

  it('falls back to a translated message when the import fails without an Error', async () => {
    vi.mocked(importTranscriptJson).mockRejectedValue('boom');
    renderModal();

    fireEvent.click(screen.getByTestId('import-tab-paste'));
    fireEvent.change(screen.getByTestId('import-paste-textarea'), { target: { value: '{"a":1}' } });
    fireEvent.click(screen.getByTestId('import-submit-btn'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('chat.import.importFailed'));
  });
});
