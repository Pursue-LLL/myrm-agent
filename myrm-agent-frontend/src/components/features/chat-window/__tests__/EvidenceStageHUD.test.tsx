/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import React from 'react';
import { EvidenceStageHUD } from '../EvidenceStageHUD';
import type { ProgressItem } from '@/store/chat/types/progress';

vi.mock('next-intl', () => ({
  useTranslations: (namespace?: string) => (key: string, params?: Record<string, unknown>) => {
    if (params?.count !== undefined) {
      return `${namespace || 'common'}.${key}:${params.count}`;
    }
    return `${namespace || 'common'}.${key}`;
  },
}));

describe('EvidenceStageHUD Component', () => {
  it('returns null when steps array is empty', () => {
    const { container } = render(<EvidenceStageHUD steps={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders all four stages (prepared, executing, observed, verified) for active workflow', () => {
    const steps: ProgressItem[] = [
      {
        step_key: 'plan_1',
        is_plan: true,
        reason: 'Declare task roadmap',
      },
      {
        step_key: 'tool_edit',
        tool_name: 'edit_file',
        status: 'success',
        duration_ms: 120,
        stdout: 'Updated 1 file, +15 lines',
      },
    ];

    render(<EvidenceStageHUD steps={steps} loading={false} />);

    expect(screen.getByTestId('evidence-stage-hud')).toBeInTheDocument();
    expect(screen.getByTestId('evidence-stage-prepared')).toBeInTheDocument();
    expect(screen.getByTestId('evidence-stage-executing')).toBeInTheDocument();
    expect(screen.getByTestId('evidence-stage-observed')).toBeInTheDocument();
    expect(screen.getByTestId('evidence-stage-verified')).toBeInTheDocument();
  });

  it('marks verified stage as success when verification tool passes', () => {
    const steps: ProgressItem[] = [
      {
        step_key: 'tool_test',
        tool_name: 'run_pytest',
        status: 'success',
        duration_ms: 450,
        stdout: '3 passed in 0.45s',
      },
    ];

    render(<EvidenceStageHUD steps={steps} loading={false} />);

    const verifiedPill = screen.getByTestId('evidence-stage-verified');
    expect(verifiedPill).toBeInTheDocument();
    expect(verifiedPill).toHaveTextContent('evidenceStageHUD.stages.verified.label');
  });

  it('toggles evidence snapshot drawer and filters by clicked stage', () => {
    const steps: ProgressItem[] = [
      {
        step_key: 'plan_step',
        is_plan: true,
        reason: 'Refactor authentication token validation',
      },
      {
        step_key: 'tool_edit',
        tool_name: 'edit_file',
        status: 'success',
        duration_ms: 150,
        stdout: 'Modified auth.py',
      },
      {
        step_key: 'tool_verify',
        tool_name: 'pytest_runner',
        status: 'success',
        duration_ms: 800,
        stdout: '4 passed in 0.8s',
      },
    ];

    render(<EvidenceStageHUD steps={steps} loading={false} defaultExpanded={false} />);

    // Initially drawer should not be rendered
    expect(screen.queryByTestId('evidence-snapshot-drawer')).toBeNull();

    // Click toggle button to expand
    const toggleBtn = screen.getByTestId('evidence-hud-toggle');
    fireEvent.click(toggleBtn);

    expect(screen.getByTestId('evidence-snapshot-drawer')).toBeInTheDocument();
    expect(screen.getAllByTestId('evidence-step-card').length).toBe(2);

    // Click verified stage pill to filter to verified steps
    const verifiedStageBtn = screen.getByTestId('evidence-stage-verified');
    fireEvent.click(verifiedStageBtn);

    const cards = screen.getAllByTestId('evidence-step-card');
    expect(cards.length).toBe(1);
    expect(cards[0]).toHaveTextContent('pytest_runner');
    expect(cards[0]).toHaveTextContent('4 passed in 0.8s');
  });
});
