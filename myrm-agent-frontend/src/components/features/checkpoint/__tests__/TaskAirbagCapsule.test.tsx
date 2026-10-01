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

  it('renders armed status and opens rollback modal on click', async () => {
    vi.mocked(airbagService.getAirbagStatus).mockResolvedValueOnce({
      taskId: 'task-100',
      totalFilesChanged: 3,
      modifiedFiles: ['src/app.ts'],
      addedFiles: ['src/new.ts'],
      deletedFiles: ['old.ts'],
      externalEffects: ['docker run postgres'],
      canRollback: true,
    });

    render(<TaskAirbagCapsule taskId="task-100" workspacePath="/tmp/ws" />);

    await waitFor(() => {
      expect(screen.getByText('安全气囊已就绪')).toBeInTheDocument();
      expect(screen.getByText('3 项变更')).toBeInTheDocument();
    });

    // Open modal
    const reviewBtn = screen.getByText('审查/复原');
    fireEvent.click(reviewBtn);

    expect(screen.getByText('时光倒流 · 安全气囊审查')).toBeInTheDocument();
    expect(screen.getByText('docker run postgres')).toBeInTheDocument();
    expect(screen.getByText('src/app.ts')).toBeInTheDocument();
  });

  it('triggers rollback successfully', async () => {
    vi.mocked(airbagService.getAirbagStatus).mockResolvedValueOnce({
      taskId: 'task-rollback',
      totalFilesChanged: 1,
      modifiedFiles: ['file.txt'],
      addedFiles: [],
      deletedFiles: [],
      externalEffects: [],
      canRollback: true,
    });
    vi.mocked(airbagService.rollbackAirbag).mockResolvedValueOnce({
      success: true,
      taskId: 'task-rollback',
      status: 'rolled_back',
    });

    render(<TaskAirbagCapsule taskId="task-rollback" />);

    await waitFor(() => {
      expect(screen.getByText('审查/复原')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('审查/复原'));

    const rollbackBtn = screen.getByText('时光倒流·完整复原');
    fireEvent.click(rollbackBtn);

    await waitFor(() => {
      expect(airbagService.rollbackAirbag).toHaveBeenCalledWith('task-rollback', undefined);
    });
  });
});
