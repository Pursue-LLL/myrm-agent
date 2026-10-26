/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { confirmAction } from '@/lib/app-dialog';
import type { CheckpointInfo } from '@/services/checkpoint';
import CheckpointCard from '../CheckpointCard';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('@/lib/app-dialog', () => ({ confirmAction: vi.fn() }));

const checkpoint: CheckpointInfo = {
  taskId: 'task-1',
  agentType: 'researcher',
  sessionId: 'session-1',
  timestamp: 1_710_000_000,
  progress: 0.5,
  lastTool: null,
  taskDescription: 'Compile the report',
};

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

describe('CheckpointCard delete', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('deletes the checkpoint once the user confirms', async () => {
    vi.mocked(confirmAction).mockResolvedValue(true);
    const onDelete = vi.fn().mockResolvedValue(undefined);
    render(<CheckpointCard checkpoint={checkpoint} onReinitiate={vi.fn()} onDelete={onDelete} />);

    fireEvent.click(screen.getByRole('button', { name: 'delete' }));

    await waitFor(() => expect(onDelete).toHaveBeenCalledExactlyOnceWith('task-1'));
    expect(confirmAction).toHaveBeenCalledExactlyOnceWith({
      variant: 'destructive',
      description: 'confirmDelete',
      confirmText: 'delete',
    });
  });

  it('keeps the checkpoint, and the button usable, when the user declines', async () => {
    vi.mocked(confirmAction).mockResolvedValue(false);
    const onDelete = vi.fn();
    render(<CheckpointCard checkpoint={checkpoint} onReinitiate={vi.fn()} onDelete={onDelete} />);

    fireEvent.click(screen.getByRole('button', { name: 'delete' }));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(1));
    await settle();

    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'delete' })).toBeEnabled();
  });

  it('shows no deleting state while the question is still open', async () => {
    vi.mocked(confirmAction).mockReturnValue(new Promise(() => undefined));
    render(<CheckpointCard checkpoint={checkpoint} onReinitiate={vi.fn()} onDelete={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'delete' }));
    await settle();

    expect(screen.queryByText('deleting')).toBeNull();
  });
});
