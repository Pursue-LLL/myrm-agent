import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ActiveSubagentSwimlanesBar } from '../ActiveSubagentSwimlanesBar';
import { useInFlightSteerStore } from '../useInFlightSteerStore';

vi.mock('@/services/background-tasks', () => ({
  steerBackgroundTask: vi.fn().mockResolvedValue({ message: 'ok', task_id: 't-1' }),
  cancelBackgroundTask: vi.fn().mockResolvedValue({ message: 'ok', task_id: 't-1' }),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('ActiveSubagentSwimlanesBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useInFlightSteerStore.getState().clearSwimlanes();
  });

  it('renders nothing when there are no active subagents', () => {
    const { container } = render(<ActiveSubagentSwimlanesBar />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders active subagent swimlane cards with status, tokens and timing', () => {
    useInFlightSteerStore.getState().registerSwimlane({
      id: 'agent-1',
      name: 'Data Analyst',
      role: 'Analyst',
      status: 'running',
      currentStep: 'Computing aggregations',
      tokensUsed: 4200,
      elapsedSeconds: 35,
    });

    render(<ActiveSubagentSwimlanesBar />);

    expect(screen.getByText(/活跃专家泳道 \(1\)/)).toBeInTheDocument();
    expect(screen.getByText('Data Analyst')).toBeInTheDocument();
    expect(screen.getByText('Analyst')).toBeInTheDocument();
    expect(screen.getByText('Computing aggregations')).toBeInTheDocument();
    expect(screen.getByText('4.2k')).toBeInTheDocument();
    expect(screen.getByText('35s')).toBeInTheDocument();
  });

  it('toggles steer popover on button click', () => {
    useInFlightSteerStore.getState().registerSwimlane({
      id: 'agent-2',
      name: 'Security Bot',
      role: 'SecOps',
      status: 'running',
      currentStep: 'Auditing API scopes',
      tokensUsed: 950,
      elapsedSeconds: 12,
    });

    render(<ActiveSubagentSwimlanesBar />);

    expect(screen.queryByRole('dialog', { name: /纠偏子代理: Security Bot/ })).not.toBeInTheDocument();

    const steerBtn = screen.getByRole('button', { name: '纠偏' });
    fireEvent.click(steerBtn);

    expect(screen.getByRole('dialog', { name: /纠偏子代理: Security Bot/ })).toBeInTheDocument();
    expect(useInFlightSteerStore.getState().activePopoverSubagentId).toBe('agent-2');

    // Click again to close
    fireEvent.click(steerBtn);
    expect(screen.queryByRole('dialog', { name: /纠偏子代理: Security Bot/ })).not.toBeInTheDocument();
  });
});
