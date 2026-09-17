/** @vitest-environment jsdom */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryDomainMeshPanel } from '../mesh/MemoryDomainMeshPanel';
import * as domainMeshService from '@/services/memory/domainMesh';

vi.mock('@/services/memory/domainMesh', () => ({
  getDomainMeshOverview: vi.fn(),
  getMemoryDrillDown: vi.fn(),
  migrateFromHermes: vi.fn(),
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: vi.fn(),
}));

const mockOverview: domainMeshService.DomainMeshOverviewResponse = {
  total_memories: 3,
  user: {
    domain: 'user',
    total_count: 1,
    category_counts: { preferences: 1 },
    highlights: [
      {
        id: 'user-1',
        l0: 'Dark mode user preference',
        l1: 'User prefers dark theme with high contrast',
        category: 'preferences',
        memory_type: 'semantic',
        updated_at: '2026-09-18T00:00:00Z',
      },
    ],
  },
  assistant: {
    domain: 'assistant',
    total_count: 1,
    category_counts: { soul: 1 },
    highlights: [
      {
        id: 'asst-1',
        l0: 'Calm assistant persona',
        l1: 'Assistant always responds politely and concisely',
        category: 'soul',
        memory_type: 'semantic',
        updated_at: '2026-09-18T00:00:00Z',
      },
    ],
  },
  task: {
    domain: 'task',
    total_count: 1,
    category_counts: { traps: 1 },
    highlights: [
      {
        id: 'task-1',
        l0: 'Avoid destructive git reset',
        l1: 'Never use git reset without uncommitted work review',
        category: 'traps',
        memory_type: 'procedural',
        updated_at: '2026-09-18T00:00:00Z',
      },
    ],
  },
};

describe('MemoryDomainMeshPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(domainMeshService.getDomainMeshOverview).mockResolvedValue(mockOverview);
  });

  it('renders three domain cards and their highlights', async () => {
    render(<MemoryDomainMeshPanel />);

    expect(screen.getByText('Three-Domain Progressive Memory Mesh')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('User Domain')).toBeInTheDocument();
      expect(screen.getByText('Assistant Domain')).toBeInTheDocument();
      expect(screen.getByText('Task Domain')).toBeInTheDocument();
    });

    expect(screen.getByText('Dark mode user preference')).toBeInTheDocument();
    expect(screen.getByText('Calm assistant persona')).toBeInTheDocument();
    expect(screen.getByText('Avoid destructive git reset')).toBeInTheDocument();
  });

  it('opens drill-down dialog when a highlight card is clicked', async () => {
    vi.mocked(domainMeshService.getMemoryDrillDown).mockResolvedValue({
      id: 'user-1',
      domain: 'user',
      category: 'preferences',
      memory_type: 'semantic',
      l0: 'Dark mode user preference',
      l1: 'User prefers dark theme with high contrast',
      l2_content: 'Full verbatim text of the dark mode preference item.',
      created_at: '2026-09-18T00:00:00Z',
      updated_at: '2026-09-18T00:00:00Z',
      metadata: {},
    });

    render(<MemoryDomainMeshPanel />);

    await waitFor(() => {
      expect(screen.getByText('Dark mode user preference')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Dark mode user preference'));

    await waitFor(() => {
      expect(screen.getByText('Progressive Memory Drill-Down')).toBeInTheDocument();
      expect(
        screen.getByText('Full verbatim text of the dark mode preference item.')
      ).toBeInTheDocument();
    });
  });

  it('opens migration modal when Migrate from Hermes is clicked', async () => {
    render(<MemoryDomainMeshPanel />);

    await waitFor(() => {
      expect(screen.getByText('User Domain')).toBeInTheDocument();
    });

    const migrateBtn = screen.getByText('Migrate from Hermes');
    fireEvent.click(migrateBtn);

    await waitFor(() => {
      expect(screen.getByText('Import from Hermes or OpenViking')).toBeInTheDocument();
      expect(screen.getByText('Start Lossless Import')).toBeInTheDocument();
    });
  });
});
