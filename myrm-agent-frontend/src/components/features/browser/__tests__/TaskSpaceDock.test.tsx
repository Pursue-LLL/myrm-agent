'use client';

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { TaskSpaceDock } from '../TaskSpaceDock';
import * as api from '@/services/browserTaskSpaces';

vi.mock('@/services/browserTaskSpaces', () => ({
  fetchTaskSpaces: vi.fn(),
  closeTaskSpace: vi.fn(),
  toggleTaskSpaceTakeover: vi.fn(),
  fetchTaskSpaceSnapshot: vi.fn(),
}));

describe('TaskSpaceDock Component', () => {
  const mockSpaces: api.TaskSpaceInfo[] = [
    {
      space_id: 'space-alpha',
      name: 'Search Space A',
      status: 'idle',
      chat_id: 'chat-123',
      created_at: 1000,
      last_accessed_at: 1000,
      idle_seconds: 15.0,
      active_pages: 2,
      takeover_active: false,
      current_url: 'https://example.com',
      current_title: 'Example Domain',
      metadata: {},
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when space list is empty', async () => {
    vi.mocked(api.fetchTaskSpaces).mockResolvedValueOnce([]);
    const { container } = render(<TaskSpaceDock autoRefreshIntervalMs={0} />);
    await waitFor(() => {
      expect(api.fetchTaskSpaces).toHaveBeenCalled();
    });
    expect(container.firstChild).toBeNull();
  });

  it('renders minimized dock pill when spaces exist and expands on click', async () => {
    vi.mocked(api.fetchTaskSpaces).mockResolvedValue(mockSpaces);
    render(<TaskSpaceDock autoRefreshIntervalMs={0} />);

    await waitFor(() => {
      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    // Expand
    const pill = screen.getByRole('button');
    fireEvent.click(pill);

    expect(screen.getByText('Search Space A')).toBeInTheDocument();
    expect(screen.getByText('Example Domain')).toBeInTheDocument();
  });

  it('toggles takeover state on button click', async () => {
    vi.mocked(api.fetchTaskSpaces).mockResolvedValue(mockSpaces);
    vi.mocked(api.toggleTaskSpaceTakeover).mockResolvedValueOnce({
      ...mockSpaces[0],
      takeover_active: true,
      status: 'takeover',
    });

    render(<TaskSpaceDock autoRefreshIntervalMs={0} />);

    await waitFor(() => {
      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button'));

    const takeoverBtn = screen.getByText('takeoverBtn');
    fireEvent.click(takeoverBtn);

    await waitFor(() => {
      expect(api.toggleTaskSpaceTakeover).toHaveBeenCalledWith('space-alpha', true);
    });
  });

  it('closes space on close button click', async () => {
    vi.mocked(api.fetchTaskSpaces).mockResolvedValue(mockSpaces);
    vi.mocked(api.closeTaskSpace).mockResolvedValueOnce(true);

    render(<TaskSpaceDock autoRefreshIntervalMs={0} />);

    await waitFor(() => {
      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button'));

    const closeBtn = screen.getByTitle('closeSpaceBtn');
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(api.closeTaskSpace).toHaveBeenCalledWith('space-alpha');
    });
  });
});
