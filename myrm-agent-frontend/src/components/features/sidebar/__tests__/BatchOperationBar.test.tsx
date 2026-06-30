import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import BatchOperationBar from '../BatchOperationBar';

const batchMoveChats = vi.hoisted(() => vi.fn());
const toastMock = vi.hoisted(() => Object.assign(vi.fn(), {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
  dismiss: vi.fn(),
}));

vi.mock('@/services/projects', () => ({
  batchMoveChats,
}));

vi.mock('@/hooks/useToast', () => ({
  toast: toastMock,
}));

vi.mock('@/store/useProjectStore', () => ({
  useProjectStore: (selector: (s: { projects: Array<{ id: string; name: string; color: string }> }) => unknown) =>
    selector({
      projects: [
        { id: 'proj-1', name: 'Project A', color: '#ff0000' },
        { id: 'proj-2', name: 'Project B', color: '#00ff00' },
      ],
    }),
}));

vi.mock('@/store/useChatStore', () => {
  const state = {
    chatHistoryItems: [
      { id: 'chat-1', projectId: null },
      { id: 'chat-2', projectId: null },
    ],
  };
  return {
    default: {
      getState: () => state,
      setState: vi.fn((partial: Record<string, unknown>) => Object.assign(state, partial)),
    },
  };
});

const defaultProps = {
  selectedCount: 2,
  totalCount: 5,
  selectedIds: new Set(['chat-1', 'chat-2']),
  onSelectAll: vi.fn(),
  onDeselectAll: vi.fn(),
  onDelete: vi.fn(),
  onExit: vi.fn(),
  t: ((key: string, params?: Record<string, unknown>) => {
    if (params?.count !== undefined) return `${key}:${params.count}`;
    return key;
  }) as ReturnType<typeof import('next-intl').useTranslations>,
};

describe('BatchOperationBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders batch operation bar with project picker toggle', () => {
    render(<BatchOperationBar {...defaultProps} />);
    expect(screen.getByText('chat.batch.selected:2')).toBeInTheDocument();
    expect(screen.getByText('project.moveTo')).toBeInTheDocument();
    expect(screen.getByText('chat.batch.delete')).toBeInTheDocument();
  });

  it('shows project picker when moveTo is clicked', async () => {
    const user = userEvent.setup();
    render(<BatchOperationBar {...defaultProps} />);

    await user.click(screen.getByText('project.moveTo'));
    expect(screen.getByText('Project A')).toBeInTheDocument();
    expect(screen.getByText('Project B')).toBeInTheDocument();
    expect(screen.getByText('project.removeFromProject')).toBeInTheDocument();
  });

  it('calls batchMoveChats and shows success toast on successful move', async () => {
    batchMoveChats.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    render(<BatchOperationBar {...defaultProps} />);

    await user.click(screen.getByText('project.moveTo'));
    await user.click(screen.getByText('Project A'));

    await waitFor(() => {
      expect(batchMoveChats).toHaveBeenCalledWith(['chat-1', 'chat-2'], 'proj-1');
    });

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith('project.moveSuccess:2');
    });
  });

  it('shows error toast on failed move', async () => {
    batchMoveChats.mockRejectedValueOnce(new Error('Network error'));
    const user = userEvent.setup();
    render(<BatchOperationBar {...defaultProps} />);

    await user.click(screen.getByText('project.moveTo'));
    await user.click(screen.getByText('Project A'));

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith({
        title: 'project.moveFailed',
        description: 'Network error',
        variant: 'destructive',
      });
    });
  });

  it('disables project buttons during move operation', async () => {
    let resolveMove: () => void;
    batchMoveChats.mockReturnValueOnce(
      new Promise<void>((resolve) => {
        resolveMove = resolve;
      }),
    );

    const user = userEvent.setup();
    render(<BatchOperationBar {...defaultProps} />);

    await user.click(screen.getByText('project.moveTo'));
    await user.click(screen.getByText('Project A'));

    await waitFor(() => {
      const projectButtons = screen.getAllByRole('button').filter((btn) => btn.hasAttribute('disabled'));
      expect(projectButtons.length).toBeGreaterThan(0);
    });

    resolveMove!();

    await waitFor(() => {
      expect(batchMoveChats).toHaveBeenCalledTimes(1);
    });
  });

  it('prevents duplicate move calls while moving', async () => {
    let resolveMove: () => void;
    batchMoveChats.mockReturnValueOnce(
      new Promise<void>((resolve) => {
        resolveMove = resolve;
      }),
    );

    const user = userEvent.setup();
    render(<BatchOperationBar {...defaultProps} />);

    await user.click(screen.getByText('project.moveTo'));
    const projectAButton = screen.getByText('Project A');
    await user.click(projectAButton);

    await waitFor(() => {
      expect(projectAButton).toBeDisabled();
    });

    expect(batchMoveChats).toHaveBeenCalledTimes(1);

    resolveMove!();

    await waitFor(() => {
      expect(batchMoveChats).toHaveBeenCalledTimes(1);
    });
  });

  it('closes project picker after move (success or failure)', async () => {
    batchMoveChats.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    render(<BatchOperationBar {...defaultProps} />);

    await user.click(screen.getByText('project.moveTo'));
    expect(screen.getByText('Project A')).toBeInTheDocument();

    await user.click(screen.getByText('Project A'));

    await waitFor(() => {
      expect(screen.queryByText('Project A')).not.toBeInTheDocument();
    });
  });
});
