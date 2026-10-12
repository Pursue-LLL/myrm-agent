import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MemoryConflictChatBanner from '../MemoryConflictChatBanner';
import { useMemoryStore } from '@/store/memory';

describe('MemoryConflictChatBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMemoryStore.setState({
      conflictCount: 0,
      conflicts: [],
      fetchConflicts: vi.fn(),
    });
    if (typeof window !== 'undefined') {
      window.sessionStorage.clear();
    }
  });

  it('renders nothing when there are no conflicts', () => {
    const { container } = render(<MemoryConflictChatBanner chatId="chat-1" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders banner when conflicts exist', () => {
    useMemoryStore.setState({ conflictCount: 2 });
    render(<MemoryConflictChatBanner chatId="chat-1" />);
    expect(screen.getByTestId('memory-conflict-chat-banner')).toBeInTheDocument();
  });
});
