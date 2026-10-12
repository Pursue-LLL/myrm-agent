/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { buildAnchor } from '@/lib/artifacts/artifactAnnotations';
import { useArtifactAnnotationStore } from '@/store/useArtifactAnnotationStore';

const mocks = vi.hoisted(() => ({
  sendMessage: vi.fn<(...args: unknown[]) => Promise<boolean>>(),
  toastError: vi.fn(),
  t: (key: string, values?: Record<string, unknown>) => (typeof values?.fallback === 'string' ? values.fallback : key),
}));

vi.mock('next-intl', () => ({ useTranslations: () => mocks.t }));
vi.mock('@/store/useChatStore', () => ({
  default: { getState: () => ({ sendMessage: (...args: unknown[]) => mocks.sendMessage(...args) }) },
}));
vi.mock('@/services/kanban', () => ({
  addComment: vi.fn(),
  listBoards: vi.fn(),
  listTasks: vi.fn(),
  rejectTask: vi.fn(),
}));
vi.mock('@/hooks/shared/useToast', () => ({
  toast: { error: mocks.toastError, success: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import { ArtifactAnnotationPanel } from '../ArtifactAnnotationPanel';

const CONTENT = 'line one\nline two\nline three';
const STORAGE_KEY = 'myrm.artifact-annotations.v1';

function seedOpenAnnotation(): void {
  // The panel re-hydrates from storage on mount, so the seed has to live there.
  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      'art-1': [
        {
          id: 'a1',
          artifactId: 'art-1',
          versionId: 'v1',
          anchor: buildAnchor(CONTENT, 2, 2),
          intent: 'Tighten this sentence',
          status: 'open',
          createdAt: new Date().toISOString(),
        },
      ],
    }),
  );
}

const statusOfAnnotation = () => useArtifactAnnotationStore.getState().byArtifact['art-1']?.[0]?.status;

function renderPanel(): void {
  render(
    <ArtifactAnnotationPanel
      artifactId="art-1"
      artifactName="doc.md"
      content={CONTENT}
      versionId="v1"
      versionCount={1}
    />,
  );
}

async function clickSendForRevision(): Promise<void> {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /Send for revision/ }));
  });
}

describe('ArtifactAnnotationPanel send for revision', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.sendMessage.mockReset();
    window.localStorage.clear();
    seedOpenAnnotation();
  });

  it('marks the comment submitted once the chat took the revision request', async () => {
    mocks.sendMessage.mockResolvedValueOnce(true);
    renderPanel();

    await clickSendForRevision();

    expect(statusOfAnnotation()).toBe('submitted');
  });

  it('leaves the comment open when the chat refused the request, so it can be sent again', async () => {
    mocks.sendMessage.mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    renderPanel();

    await clickSendForRevision();
    expect(statusOfAnnotation()).toBe('open');

    await clickSendForRevision();
    expect(mocks.sendMessage).toHaveBeenCalledTimes(2);
    expect(statusOfAnnotation()).toBe('submitted');
  });

  it('reports a send that failed and leaves the comment open', async () => {
    mocks.sendMessage.mockRejectedValueOnce(new Error('offline'));
    renderPanel();

    await clickSendForRevision();

    expect(mocks.toastError).toHaveBeenCalledWith('Failed to send review feedback.');
    expect(statusOfAnnotation()).toBe('open');
  });
});
