import React from 'react';
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { OwnerActionRiskCard } from '../OwnerActionRiskCard';
import { useSwarmExecutionStore } from '@/components/features/swarm/useSwarmExecutionStore';
import type { OwnerRiskItem } from '@/components/features/swarm/swarmTypes';

describe('OwnerActionRiskCard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useSwarmExecutionStore.getState().reset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const mockRisks: OwnerRiskItem[] = [
    {
      riskId: 'risk_voltage',
      title: 'Commercial Steam Oven Voltage',
      description: 'May exceed 40kW electrical budget',
      severity: 'high',
      isConfirmed: false,
      externalConstraintType: 'property_utility',
      remediationHint: 'Contact property manager for capacity upgrade',
    },
  ];

  it('renders nothing when no risks exist', () => {
    const { container } = render(<OwnerActionRiskCard chatId="chat_01" risks={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders card header and progress cue when risks are provided', () => {
    render(<OwnerActionRiskCard chatId="chat_01" risks={mockRisks} />);

    expect(screen.getByRole('button', { name: 'riskChecklistAriaLabel' })).toBeDefined();
    expect(screen.getByText('ownerRiskCardTitle')).toBeDefined();
    expect(screen.getByText('Commercial Steam Oven Voltage')).toBeDefined();
    expect(screen.getByText('verifyNow')).toBeDefined();
  });

  it('confirms risk on check button click', () => {
    useSwarmExecutionStore.setState({ ownerRisks: mockRisks });
    render(<OwnerActionRiskCard chatId="chat_01" />);

    const confirmBtn = screen.getByRole('button', { name: 'markConfirmed' });
    fireEvent.click(confirmBtn);

    const updatedRisks = useSwarmExecutionStore.getState().ownerRisks;
    expect(updatedRisks[0].isConfirmed).toBe(true);
    expect(updatedRisks[0].confirmedBy).toBe('store_owner');
  });
});
