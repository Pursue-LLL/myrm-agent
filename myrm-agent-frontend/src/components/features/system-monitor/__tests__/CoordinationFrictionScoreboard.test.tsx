import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CoordinationFrictionScoreboard } from '../CoordinationFrictionScoreboard';
import { SupervisionDecayChart } from '../SupervisionDecayChart';
import type { CoordinationScoreboardSummary } from '../types';

describe('CoordinationFrictionScoreboard & SupervisionDecayChart', () => {
  const mockSummary: CoordinationScoreboardSummary = {
    template_type: 'global',
    total_runs: 24,
    average_friction_rate: 2.4,
    rework_rate_pct: 16.7,
    total_coordination_hours_saved: 38.5,
    friction_decay_pct: -82.5,
    active_templates: ['broadcast_prep', 'channel_deal', 'code_refactor'],
    decay_curve: [
      {
        sequence_number: 1,
        intervention_rate_pct: 85.0,
        average_attention_minutes: 42.0,
        sample_count: 8,
      },
      {
        sequence_number: 2,
        intervention_rate_pct: 45.0,
        average_attention_minutes: 21.0,
        sample_count: 8,
      },
      {
        sequence_number: 3,
        intervention_rate_pct: 12.0,
        average_attention_minutes: 6.0,
        sample_count: 8,
      },
    ],
    updated_at: '2026-10-12T10:00:00Z',
  };

  it('renders 4 core KPI cards, headers, and tangible outcomes', () => {
    render(<CoordinationFrictionScoreboard summary={mockSummary} />);

    expect(screen.getByText('人机协调摩擦度量与监督衰减记分板')).toBeInTheDocument();
    expect(screen.getByText(/2.4/)).toBeInTheDocument();
    expect(screen.getByText(/16.7%/)).toBeInTheDocument();
    expect(screen.getByText(/38.5/)).toBeInTheDocument();
    expect(screen.getByText(/-82.5%/)).toBeInTheDocument();
    expect(screen.getByText(/真实业务成效验证/)).toBeInTheDocument();
  });

  it('renders supervision decay pillars and sequence labels', () => {
    render(<SupervisionDecayChart points={mockSummary.decay_curve} />);

    expect(screen.getByText('重复场景人工监督衰减曲线 (Supervision Decay Curve)')).toBeInTheDocument();
    expect(screen.getByText('第 1 轮')).toBeInTheDocument();
    expect(screen.getByText('第 2 轮')).toBeInTheDocument();
    expect(screen.getByText('第 3 轮')).toBeInTheDocument();
    expect(screen.getByText('85%')).toBeInTheDocument();
    expect(screen.getByText('12%')).toBeInTheDocument();
  });

  it('triggers onSelectTemplate when dropdown changes', () => {
    const handleSelect = vi.fn();
    render(<CoordinationFrictionScoreboard summary={mockSummary} onSelectTemplate={handleSelect} />);

    const select = screen.getByTestId('template-selector');
    fireEvent.change(select, { target: { value: 'broadcast_prep' } });

    expect(handleSelect).toHaveBeenCalledWith('broadcast_prep');
  });

  it('renders empty placeholder when decay points array is empty', () => {
    render(<SupervisionDecayChart points={[]} />);
    expect(screen.getByTestId('supervision-decay-empty')).toBeInTheDocument();
  });
});
