/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { GovernanceOverview } from '@/services/agent';

const swrState = vi.hoisted(() => ({
  value: { data: undefined as GovernanceOverview | undefined, isLoading: false, mutate: vi.fn() },
}));

vi.mock('swr', () => ({ default: () => swrState.value }));
vi.mock('@/services/agent', () => ({ deleteAgent: vi.fn(), getGovernanceOverview: vi.fn() }));
vi.mock('@/components/agent/GovernanceMergeWizard', () => ({ MergeWizard: () => null }));

import { GovernancePanel } from '../GovernancePanel';

function renderPanel() {
  return render(<GovernancePanel agentNames={{}} onReview={vi.fn()} onChanged={vi.fn()} />);
}

describe('GovernancePanel accessible name', () => {
  it('labels the health-check region from translations when attention is needed', () => {
    swrState.value = {
      data: { total: 1, needs_attention: true, agents: [], orphans: [], overlaps: [] },
      isLoading: false,
      mutate: vi.fn(),
    };
    renderPanel();

    expect(screen.getByRole('region', { name: 'regionLabel' })).toBeInTheDocument();
  });

  it('renders nothing when no agent needs attention', () => {
    swrState.value = {
      data: { total: 1, needs_attention: false, agents: [], orphans: [], overlaps: [] },
      isLoading: false,
      mutate: vi.fn(),
    };
    const { container } = renderPanel();

    expect(container).toBeEmptyDOMElement();
  });
});
