import React from 'react';
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRecallBadgeHUD } from '../MemoryRecallBadgeHUD';
import { useSwarmExecutionStore } from '@/components/features/swarm/useSwarmExecutionStore';
import type { RecalledRuleItem } from '@/components/features/swarm/swarmTypes';

describe('MemoryRecallBadgeHUD', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useSwarmExecutionStore.getState().reset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const mockRules: RecalledRuleItem[] = [
    {
      ruleId: 'r_vegan',
      summary: 'Vegan menu required for catering',
      sourceTurnId: 'turn_03',
      confidence: 0.95,
      isActive: true,
      category: 'catering',
    },
    {
      ruleId: 'r_closing',
      summary: 'Store closes at 22:00 sharp',
      sourceTurnId: 'turn_01',
      confidence: 0.9,
      isActive: false,
      category: 'schedule',
    },
  ];

  it('renders nothing when no rules exist', () => {
    const { container } = render(<MemoryRecallBadgeHUD chatId="chat_01" rules={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders top HUD badge when rules are present', () => {
    render(<MemoryRecallBadgeHUD chatId="chat_01" rules={mockRules} />);

    expect(screen.getByRole('button', { name: 'recallBadgeAriaLabel' })).toBeDefined();
    expect(screen.getByText('viewDetails')).toBeDefined();
  });

  it('expands inspector panel on click and toggles rule active state', () => {
    useSwarmExecutionStore.setState({ recalledRules: mockRules });
    render(<MemoryRecallBadgeHUD chatId="chat_01" />);

    const trigger = screen.getByRole('button', { name: 'recallBadgeAriaLabel' });
    fireEvent.click(trigger);

    expect(screen.getByText('Vegan menu required for catering')).toBeDefined();
    expect(screen.getByText('Store closes at 22:00 sharp')).toBeDefined();

    // Toggle rule
    const disableBtn = screen.getByRole('button', { name: 'disableRule' });
    fireEvent.click(disableBtn);

    const updatedRules = useSwarmExecutionStore.getState().recalledRules;
    expect(updatedRules.find((r) => r.ruleId === 'r_vegan')?.isActive).toBe(false);
  });
});
