/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import FileSnapshotList from '../FileSnapshotList';

const { toastMock, createFileSnapshotMock, listFileSnapshotsMock } = vi.hoisted(() => ({
  toastMock: vi.fn(),
  createFileSnapshotMock: vi.fn(),
  listFileSnapshotsMock: vi.fn(),
}));

const stableT = (key: string, values?: Record<string, string | number>): string =>
  values?.count !== undefined ? `${key}:${String(values.count)}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: { success: toastMock },
}));

vi.mock('@/services/checkpoint', () => ({
  createFileSnapshot: (...args: unknown[]) => createFileSnapshotMock(...args),
  listFileSnapshots: (...args: unknown[]) => listFileSnapshotsMock(...args),
  restoreFileSnapshot: vi.fn(),
  deleteFileSnapshot: vi.fn(),
  cleanupFileSnapshots: vi.fn(),
  getFileSnapshotDiff: vi.fn(),
}));

vi.mock('@/hooks/agent/useAgentName', () => ({
  useAgentNameMap: () => new Map(),
}));

const renderList = () => render(<FileSnapshotList workingDir="/ws" />);

describe('FileSnapshotList', () => {
  beforeEach(() => {
    toastMock.mockReset();
    createFileSnapshotMock.mockReset();
    listFileSnapshotsMock.mockReset();
    listFileSnapshotsMock.mockResolvedValue({ snapshots: [], total: 0 });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('expands the create input when the create version button is clicked', async () => {
    renderList();
    fireEvent.click(screen.getByText('createVersion'));
    expect(screen.getByPlaceholderText('createPlaceholder')).toBeInTheDocument();
    expect(screen.getByText('confirmCreate')).toBeInTheDocument();
  });

  it('creates a snapshot with the entered description and refreshes the list', async () => {
    createFileSnapshotMock.mockResolvedValue({ success: true, snapshotId: 'snap-1', workingDir: '/ws' });
    renderList();

    fireEvent.click(screen.getByText('createVersion'));
    fireEvent.change(screen.getByPlaceholderText('createPlaceholder'), {
      target: { value: 'Before refactor' },
    });
    fireEvent.click(screen.getByText('confirmCreate'));

    await waitFor(() => {
      expect(createFileSnapshotMock).toHaveBeenCalledWith('/ws', 'Before refactor');
    });
    await waitFor(() => {
      expect(listFileSnapshotsMock).toHaveBeenCalled();
    });
    expect(toastMock).toHaveBeenCalledWith('createSuccess');
  });

  it('disables the create button while description is empty', async () => {
    renderList();
    fireEvent.click(screen.getByText('createVersion'));

    const createButton = screen.getByText('confirmCreate');
    expect(createButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText('createPlaceholder'), {
      target: { value: '  ' },
    });
    expect(screen.getByText('confirmCreate')).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText('createPlaceholder'), {
      target: { value: 'a label' },
    });
    expect(screen.getByText('confirmCreate')).toBeEnabled();
  });

  it('cancels without creating a snapshot', async () => {
    renderList();
    fireEvent.click(screen.getByText('createVersion'));
    fireEvent.change(screen.getByPlaceholderText('createPlaceholder'), {
      target: { value: 'Should not persist' },
    });
    fireEvent.click(screen.getByText('confirmNo'));

    expect(screen.queryByPlaceholderText('createPlaceholder')).not.toBeInTheDocument();
    expect(createFileSnapshotMock).not.toHaveBeenCalled();
  });

  it('surfaces create errors instead of silently failing', async () => {
    createFileSnapshotMock.mockRejectedValue(new Error('network'));
    renderList();

    fireEvent.click(screen.getByText('createVersion'));
    fireEvent.change(screen.getByPlaceholderText('createPlaceholder'), {
      target: { value: 'doomed' },
    });
    fireEvent.click(screen.getByText('confirmCreate'));

    await waitFor(() => {
      expect(screen.getByText('createError')).toBeInTheDocument();
    });
    expect(toastMock).not.toHaveBeenCalled();
  });
});
