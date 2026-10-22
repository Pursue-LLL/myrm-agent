/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { TaskAirbagCapsule } from '../TaskAirbagCapsule';
import * as airbagService from '@/services/airbag';

vi.mock('@/services/airbag', () => ({
  getAirbagStatus: vi.fn(),
  rollbackAirbag: vi.fn(),
  dismissAirbag: vi.fn(),
}));

const toast = vi.fn();
vi.mock('@/hooks/shared/useToast', () => ({ toast: (args: unknown) => toast(args) }));

const messages: Record<string, string> = {
  ready: 'Changes can be undone',
  review: 'Review / Undo',
  modalTitle: 'Review and undo changes',
  externalNote: 'Undo only restores workspace files.',
  undoAll: 'Undo all changes',
  keepChanges: 'Keep changes',
  undoneTitle: 'Changes undone',
  keptTitle: 'Changes kept',
  noChanges: 'No changes',
  'effects.container_cloud': 'container or cloud operations',
  'effects.publish': 'pushed or published content',
};

// Stable reference: an unstable translator re-creates the fetch callback on every render.
const stableT = (key: string, values?: Record<string, string | number>): string => {
  if (values?.count !== undefined) {
    return `${key}:${values.count}`;
  }
  if (values?.effects !== undefined) {
    return `${key}:${values.effects}`;
  }
  return messages[key] ?? key;
};
stableT.has = (key: string): boolean => key in messages;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const armedStatus = (overrides: Partial<airbagService.AirbagStatusResponse> = {}): airbagService.AirbagStatusResponse => ({
  taskId: 'task-100',
  totalFilesChanged: 3,
  modifiedFiles: ['src/app.ts'],
  addedFiles: ['src/new.ts'],
  deletedFiles: ['old.ts'],
  externalEffects: [],
  canRollback: true,
  ...overrides,
});

describe('TaskAirbagCapsule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when status is null', async () => {
    vi.mocked(airbagService.getAirbagStatus).mockRejectedValueOnce(new Error('404'));
    const { container } = render(<TaskAirbagCapsule taskId="task-null" />);
    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
  });

  it('shows the change count and opens the review dialog', async () => {
    vi.mocked(airbagService.getAirbagStatus).mockResolvedValueOnce(armedStatus());

    render(<TaskAirbagCapsule taskId="task-100" workspacePath="/tmp/ws" />);

    await waitFor(() => {
      expect(screen.getByText('Changes can be undone')).toBeInTheDocument();
      expect(screen.getByText('changeCount:3')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Review / Undo'));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Review and undo changes')).toBeInTheDocument();
    expect(screen.getByText('src/app.ts')).toBeInTheDocument();
  });

  it('always states what undo cannot reverse, and names the external operations it detected', async () => {
    vi.mocked(airbagService.getAirbagStatus).mockResolvedValueOnce(armedStatus({ externalEffects: ['container_cloud', 'publish'] }));

    render(<TaskAirbagCapsule taskId="task-100" />);
    fireEvent.click(await screen.findByText('Review / Undo'));

    expect(screen.getByText('Undo only restores workspace files.')).toBeInTheDocument();
    expect(
      screen.getByText('externalDetected:container or cloud operations, pushed or published content'),
    ).toBeInTheDocument();
  });

  it('states the limit without a detected-operations line when nothing external was seen', async () => {
    vi.mocked(airbagService.getAirbagStatus).mockResolvedValueOnce(armedStatus());

    render(<TaskAirbagCapsule taskId="task-100" />);
    fireEvent.click(await screen.findByText('Review / Undo'));

    expect(screen.getByText('Undo only restores workspace files.')).toBeInTheDocument();
    expect(screen.queryByText(/^externalDetected/)).toBeNull();
  });

  it('refetches the status when the refresh key changes', async () => {
    vi.mocked(airbagService.getAirbagStatus)
      .mockRejectedValueOnce(new Error('404'))
      .mockResolvedValueOnce(armedStatus({ totalFilesChanged: 1 }));

    const { rerender } = render(<TaskAirbagCapsule taskId="task-100" refreshKey="active:0" />);
    await waitFor(() => expect(airbagService.getAirbagStatus).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId('task-airbag-capsule')).toBeNull();

    rerender(<TaskAirbagCapsule taskId="task-100" refreshKey="active:1" />);

    expect(await screen.findByTestId('task-airbag-capsule')).toBeInTheDocument();
    expect(airbagService.getAirbagStatus).toHaveBeenCalledTimes(2);
  });

  it('does not refetch while the refresh key is unchanged', async () => {
    vi.mocked(airbagService.getAirbagStatus).mockResolvedValue(armedStatus());

    const { rerender } = render(<TaskAirbagCapsule taskId="task-100" refreshKey="active:1" />);
    await screen.findByTestId('task-airbag-capsule');
    rerender(<TaskAirbagCapsule taskId="task-100" refreshKey="active:1" />);

    expect(airbagService.getAirbagStatus).toHaveBeenCalledTimes(1);
  });

  it('ignores a slower earlier response that resolves after a newer one', async () => {
    let resolveFirst: (value: airbagService.AirbagStatusResponse) => void = () => {};
    vi.mocked(airbagService.getAirbagStatus)
      .mockReturnValueOnce(new Promise((resolve) => (resolveFirst = resolve)))
      .mockResolvedValueOnce(armedStatus({ totalFilesChanged: 5 }));

    const { rerender } = render(<TaskAirbagCapsule taskId="task-100" refreshKey="a" />);
    rerender(<TaskAirbagCapsule taskId="task-100" refreshKey="b" />);
    await screen.findByText('changeCount:5');

    resolveFirst(armedStatus({ totalFilesChanged: 1 }));

    await waitFor(() => expect(screen.getByText('changeCount:5')).toBeInTheDocument());
    expect(screen.queryByText('changeCount:1')).toBeNull();
  });

  it('undoes all changes and refreshes the capsule', async () => {
    vi.mocked(airbagService.getAirbagStatus).mockResolvedValue(armedStatus({ taskId: 'task-rollback', totalFilesChanged: 1 }));
    vi.mocked(airbagService.rollbackAirbag).mockResolvedValueOnce({
      success: true,
      taskId: 'task-rollback',
      status: 'rolled_back',
    });

    render(<TaskAirbagCapsule taskId="task-rollback" />);
    fireEvent.click(await screen.findByText('Review / Undo'));
    fireEvent.click(screen.getByText('Undo all changes'));

    await waitFor(() => {
      expect(airbagService.rollbackAirbag).toHaveBeenCalledWith('task-rollback', undefined);
      expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Changes undone' }));
    });
    await waitFor(() => expect(airbagService.getAirbagStatus).toHaveBeenCalledTimes(2));
  });

  it('hides the capsule once the user keeps the changes', async () => {
    vi.mocked(airbagService.getAirbagStatus)
      .mockResolvedValueOnce(armedStatus())
      .mockRejectedValueOnce(new Error('404'));
    vi.mocked(airbagService.dismissAirbag).mockResolvedValueOnce({ success: true, taskId: 'task-100', status: 'dismissed' });

    render(<TaskAirbagCapsule taskId="task-100" />);
    fireEvent.click(await screen.findByText('Review / Undo'));
    fireEvent.click(screen.getByText('Keep changes'));

    await waitFor(() => expect(screen.queryByTestId('task-airbag-capsule')).toBeNull());
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Changes kept' }));
  });
});
