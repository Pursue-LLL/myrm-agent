/**
 * Unit tests for SessionAccessRootsBar.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import SessionAccessRootsBar from '../SessionAccessRootsBar';
import useChatStore from '@/store/useChatStore';
import * as chatService from '@/services/chat';
import { toast } from 'sonner';

vi.mock('@/services/chat', () => ({
  revokeSessionAccessRoot: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    promise: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
    message: vi.fn(),
  }),
}));

const ACCESS_ROOTS_T: Record<string, string> = {
  label: 'Extra folders',
  readOnly: 'Read',
  writable: 'Write',
  revoke: 'Revoke access',
  revokeFailed: 'Could not revoke folder access',
  copyPath: 'Copy path',
  copied: 'Path copied',
};

const stableT = (key: string) => ACCESS_ROOTS_T[key] || key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('SessionAccessRootsBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.setState({
      chatId: 'test-chat-1',
      sessionAccessRoots: [],
    });
  });

  it('renders nothing when there are no session roots', () => {
    const { container } = render(<SessionAccessRootsBar />);
    expect(container.firstChild).toBeNull();
  });

  it('renders roots chips and handles copy path', async () => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });

    useChatStore.setState({
      chatId: 'test-chat-1',
      sessionAccessRoots: [
        { path: '/Users/test/workspace/project-a', writable: true },
        { path: '/Users/test/workspace/project-b', writable: false },
      ],
    });

    render(<SessionAccessRootsBar />);

    expect(screen.getByText('Extra folders')).toBeDefined();
    expect(screen.getByText('Write')).toBeDefined();
    expect(screen.getByText('Read')).toBeDefined();

    const copyBtn = screen.getByTitle(/\/Users\/test\/workspace\/project-a/);
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('/Users/test/workspace/project-a');
      expect(toast.success).toHaveBeenCalledWith('Path copied');
    });
  });

  it('handles revoke button click and updates store', async () => {
    (chatService.revokeSessionAccessRoot as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      session_access_roots: [],
    });

    useChatStore.setState({
      chatId: 'test-chat-1',
      sessionAccessRoots: [{ path: '/Users/test/workspace/project-a', writable: true }],
    });

    render(<SessionAccessRootsBar />);

    const revokeBtn = screen.getByTitle('Revoke access');
    fireEvent.click(revokeBtn);

    await waitFor(() => {
      expect(chatService.revokeSessionAccessRoot).toHaveBeenCalledWith(
        'test-chat-1',
        '/Users/test/workspace/project-a',
      );
      expect(useChatStore.getState().sessionAccessRoots).toEqual([]);
    });
  });
});
