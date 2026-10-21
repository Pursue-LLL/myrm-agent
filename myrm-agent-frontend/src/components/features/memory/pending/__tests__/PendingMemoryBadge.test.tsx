import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import PendingMemoryBadge from '../PendingMemoryBadge';
import { useMemoryStore } from '@/store/memory';

describe('PendingMemoryBadge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMemoryStore.setState({
      pendingCount: 0,
      conflictCount: 0,
    });
  });

  it('renders nothing when there are no pending memories or conflicts', () => {
    const { container } = render(<PendingMemoryBadge />);
    expect(container.firstChild).toBeNull();
  });

  it('renders badge with pending count', () => {
    useMemoryStore.setState({ pendingCount: 3, conflictCount: 0 });
    render(<PendingMemoryBadge />);
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('renders badge with conflict count and warning icon', () => {
    useMemoryStore.setState({ pendingCount: 0, conflictCount: 2 });
    render(<PendingMemoryBadge />);
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('caps displayed count at 99+', () => {
    useMemoryStore.setState({ pendingCount: 100, conflictCount: 0 });
    render(<PendingMemoryBadge />);
    expect(screen.getByText('99+')).toBeInTheDocument();
  });

  it('sums pending and conflict counts', () => {
    useMemoryStore.setState({ pendingCount: 1, conflictCount: 4 });
    render(<PendingMemoryBadge />);
    expect(screen.getByText('5')).toBeInTheDocument();
  });
});
