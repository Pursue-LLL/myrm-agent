'use client';

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { GoalState } from '../goalStatusTypes';

const stableT = (key: string) => {
  const map: Record<string, string> = {
    deliverableBundle: 'Task Deliverables',
    bundleDownloadAll: 'Download All',
    bundleDownloading: 'Downloading…',
    bundleDownloadFailed: 'Failed to download deliverables',
  };
  return map[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

const mockOpenArtifact = vi.fn();
vi.mock('@/store/useArtifactPortalStore', () => ({
  default: (selector: (s: { openArtifact: typeof mockOpenArtifact }) => unknown) =>
    selector({ openArtifact: mockOpenArtifact }),
}));

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: vi.fn(),
  getStorageUrl: (path: string) => `http://localhost:3000${path}`,
}));

vi.mock('@/components/features/artifacts/artifactUtils', () => ({
  getArtifactIcon: () => {
    const Icon = ({ className }: { className?: string }) => <svg data-testid="artifact-icon" className={className} />;
    return Icon;
  },
}));

import { TaskDeliverableBundle } from '../TaskDeliverableBundle';

const makeGoal = (overrides: Partial<GoalState> = {}): GoalState => ({
  goalId: 'goal-1',
  objective: 'Generate quarterly report',
  status: 'complete',
  tokensUsed: 50000,
  timeUsedSeconds: 300,
  deliverables: [
    { id: 'art-1', filename: 'report.docx' },
    { id: 'art-2', filename: 'slides.pptx' },
    { id: 'art-3', filename: 'data.xlsx' },
  ],
  ...overrides,
});

describe('TaskDeliverableBundle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders deliverable list when goal is complete with 2+ items', () => {
    render(<TaskDeliverableBundle goal={makeGoal()} chatId="chat-1" />);
    expect(screen.getByText('Task Deliverables')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('report.docx')).toBeInTheDocument();
    expect(screen.getByText('slides.pptx')).toBeInTheDocument();
    expect(screen.getByText('data.xlsx')).toBeInTheDocument();
  });

  it('returns null when deliverables is empty or has < 2 items', () => {
    const { container: c1 } = render(<TaskDeliverableBundle goal={makeGoal({ deliverables: [] })} chatId="chat-1" />);
    expect(c1.firstChild).toBeNull();

    const { container: c2 } = render(
      <TaskDeliverableBundle goal={makeGoal({ deliverables: [{ id: '1', filename: 'a.txt' }] })} chatId="chat-1" />,
    );
    expect(c2.firstChild).toBeNull();
  });

  it('returns null when goal is not complete', () => {
    const { container } = render(<TaskDeliverableBundle goal={makeGoal({ status: 'active' })} chatId="chat-1" />);
    expect(container.firstChild).toBeNull();
  });

  it('opens artifact portal on item click', () => {
    render(<TaskDeliverableBundle goal={makeGoal()} chatId="chat-1" />);
    fireEvent.click(screen.getByText('report.docx'));
    expect(mockOpenArtifact).toHaveBeenCalledTimes(1);
    expect(mockOpenArtifact).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'art-1',
        filename: 'report.docx',
        type: 'word_document',
        content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      }),
    );
  });

  it('downloads ZIP when Download All is clicked', async () => {
    const { fetchWithTimeout } = await import('@/lib/api');
    const mockBlob = new Blob(['zip-content'], { type: 'application/zip' });
    (fetchWithTimeout as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(mockBlob),
    });

    const createObjectURL = vi.fn(() => 'blob:fake-url');
    const revokeObjectURL = vi.fn();
    Object.defineProperty(global, 'URL', {
      value: { createObjectURL, revokeObjectURL },
      writable: true,
    });

    render(<TaskDeliverableBundle goal={makeGoal()} chatId="chat-1" />);
    fireEvent.click(screen.getByText('Download All'));

    await waitFor(() => {
      expect(fetchWithTimeout).toHaveBeenCalledWith(
        '/artifacts/download-bundle',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            artifact_ids: ['art-1', 'art-2', 'art-3'],
            chat_id: 'chat-1',
          }),
        }),
      );
    });
  });

  it('shows error toast on download failure', async () => {
    const { fetchWithTimeout } = await import('@/lib/api');
    const { toast } = await import('sonner');
    (fetchWithTimeout as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: false });

    render(<TaskDeliverableBundle goal={makeGoal()} chatId="chat-1" />);
    fireEvent.click(screen.getByText('Download All'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to download deliverables');
    });
  });
});
