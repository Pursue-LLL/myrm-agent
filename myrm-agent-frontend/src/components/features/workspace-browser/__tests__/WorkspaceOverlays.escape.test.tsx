/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FileEntry } from '@/services/chat';
import { ContextMenu } from '../WorkspaceContextMenu';
import { DeleteConfirmDialog, MoveDialog } from '../WorkspaceDialogs';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('@/services/chat', () => ({
  moveInWorkspace: vi.fn(),
}));

const NODE: FileEntry = {
  name: 'Hello.ts',
  path: '/vault/chat-1/Hello.ts',
  type: 'file',
  size: 10,
  mtime: null,
  is_text: true,
  children: null,
};

describe('Escape on the overlays of the workspace browser', () => {
  const host = vi.fn();

  beforeEach(() => {
    window.addEventListener('keydown', host);
  });

  afterEach(() => {
    window.removeEventListener('keydown', host);
    host.mockClear();
  });

  it('closes the context menu without reaching a host that also closes on Escape', () => {
    const onClose = vi.fn();
    render(
      <ContextMenu
        state={{ x: 10, y: 10, node: NODE }}
        onClose={onClose}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onMove={vi.fn()}
      />,
    );

    fireEvent.keyDown(document.body, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(host).not.toHaveBeenCalled();
  });

  it('cancels the delete confirmation without reaching the host', () => {
    const onCancel = vi.fn();
    render(<DeleteConfirmDialog node={NODE} onConfirm={vi.fn()} onCancel={onCancel} />);

    fireEvent.keyDown(document.body, { key: 'Escape' });

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(host).not.toHaveBeenCalled();
  });

  it('cancels the move dialog once, also while typing in its field', () => {
    const onCancel = vi.fn();
    render(<MoveDialog node={NODE} workspace="/vault/chat-1" onComplete={vi.fn()} onCancel={onCancel} />);

    fireEvent.keyDown(screen.getByPlaceholderText('movePlaceholder'), { key: 'Escape' });

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(host).not.toHaveBeenCalled();
  });
});
