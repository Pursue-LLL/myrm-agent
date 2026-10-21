/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import React from 'react';
import { ExecutionPhaseStepper } from '../ExecutionPhaseStepper';
import type { PhaseTransitionPayload } from '@/store/chat/types/agentStream/part1';

vi.mock('next-intl', () => ({
  useTranslations: (namespace?: string) => (key: string) => `${namespace || 'common'}.${key}`,
}));

describe('ExecutionPhaseStepper Component', () => {
  it('returns null when currentPhase and phaseHistory are empty', () => {
    const { container } = render(<ExecutionPhaseStepper />);
    expect(container.firstChild).toBeNull();
  });

  it('renders all 3 macro phases during planning', () => {
    const currentPhase: PhaseTransitionPayload = {
      phase: 'planning',
      phase_index: 1,
      active_lane: 'agent',
      node_id: 1,
      node_label: '请求理解与安全规划',
      duration_ms: 15,
    };

    render(<ExecutionPhaseStepper currentPhase={currentPhase} isStreaming />);
    expect(screen.getByText('executionPhaseStepper.phases.planning.title')).toBeInTheDocument();
    expect(screen.getByText('executionPhaseStepper.phases.executing.title')).toBeInTheDocument();
    expect(screen.getByText('executionPhaseStepper.phases.verifying.title')).toBeInTheDocument();
    expect(screen.getByText('请求理解与安全规划')).toBeInTheDocument();
  });

  it('renders execution lane badge and toggles history details', () => {
    const currentPhase: PhaseTransitionPayload = {
      phase: 'executing',
      phase_index: 2,
      active_lane: 'mcp',
      node_id: 15,
      node_label: 'MCP 外部调用: query_order',
      duration_ms: 250,
    };

    const history: PhaseTransitionPayload[] = [
      {
        phase: 'planning',
        phase_index: 1,
        active_lane: 'agent',
        node_id: 1,
        node_label: '请求意图识别',
        duration_ms: 30,
      },
      currentPhase,
    ];

    render(<ExecutionPhaseStepper currentPhase={currentPhase} phaseHistory={history} isStreaming />);

    expect(screen.getByText('executionPhaseStepper.lanes.mcp')).toBeInTheDocument();
    expect(screen.getByText('MCP 外部调用: query_order')).toBeInTheDocument();

    // Toggle expand
    const toggleButton = screen.getByTitle('executionPhaseStepper.expandTelemetry');
    fireEvent.click(toggleButton);

    expect(screen.getByText('请求意图识别')).toBeInTheDocument();
    expect(screen.getByText('#01')).toBeInTheDocument();
    expect(screen.getByText('#15')).toBeInTheDocument();
  });

  it('displays completion badge when phase is completed', () => {
    const currentPhase: PhaseTransitionPayload = {
      phase: 'completed',
      phase_index: 3,
      active_lane: 'agent',
      node_id: 30,
      node_label: '成果交付完成',
      duration_ms: 50,
    };

    render(<ExecutionPhaseStepper currentPhase={currentPhase} isStreaming={false} />);
    expect(screen.getByText('executionPhaseStepper.badge')).toBeInTheDocument();
  });
});
