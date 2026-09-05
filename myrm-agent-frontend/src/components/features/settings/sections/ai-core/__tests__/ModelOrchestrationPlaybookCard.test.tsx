import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ModelOrchestrationPlaybookCard } from '../ModelOrchestrationPlaybookCard';

// Mock next-intl
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => {
    const translations: Record<string, string> = {
      cardTitle: 'Model Orchestration Playbook',
      cardBadge: 'Playbook',
      cardSubtitle: 'Master Brain & Hands dispatch, 3-tier routing, and MoA consensus',
      viewFullPlaybook: 'View Playbook',
      collapse: 'Collapse',
      expand: 'Expand',
      miniBrainHandsTitle: 'Brain & Hands Dispatch',
      miniBrainHandsDesc: 'High reasoning planner + fast tool executor.',
      miniDynamicRoutingTitle: '3-Tier Adaptive Routing',
      miniDynamicRoutingDesc: 'Auto shift between Simple, Standard, and Reasoning tiers.',
      miniMoaTitle: 'MoA Consensus Overlay',
      miniMoaDesc: 'Cross-model validation to conquer single-model limits.',
      headerBadge: 'Orchestration Playbook',
      dialogTitle: 'Model Orchestration Playbook & Best Practices',
      dialogSubtitle: 'Learn how to optimize planning, execution, costs, and consensus',
      brainHandsTitle: '1. Brain vs. Hands Dispatch',
      brainHandsBadge: 'Cost & Speed',
      brainHandsDesc: 'Assign high-reasoning model for planning and fast model for tools.',
      brainLabel: 'Brain (Planner)',
      brainExample: 'Claude 3.7 Sonnet, DeepSeek-R1',
      handsLabel: 'Hands (Executor)',
      handsExample: 'DeepSeek-V3, Qwen 2.5',
      dynamicRoutingTitle: '2. 3-Tier Adaptive Routing',
      dynamicRoutingBadge: 'Adaptive',
      dynamicRoutingDesc: 'Automatically categorizes tasks into 3 tiers.',
      tierSimpleTitle: 'Simple Tier',
      tierSimpleDesc: 'Chit-chat & quick lookups.',
      tierStandardTitle: 'Standard Tier',
      tierStandardDesc: 'Feature coding & refactoring.',
      tierReasoningTitle: 'Reasoning Tier',
      tierReasoningDesc: 'Complex logic & math.',
      moaTitle: '3. Mixture-of-Agents (MoA) Consensus',
      moaBadge: 'Accuracy',
      moaDesc: 'Multi-model cross evaluation.',
      orthogonalTipTitle: 'Routing vs. MoA',
      orthogonalTipDesc: 'Routing saves costs, MoA raises accuracy ceilings.',
      specialistsTitle: '4. Dedicated Specialist Slots',
      specialistsDesc: 'Delegate vision, code, and long-context to specialist fallbacks.',
      footerNote: 'Configure models in Settings.',
      closeBtn: 'Close',
      configureBtn: 'Configure in Settings',
    };
    return translations[key] ?? key;
  },
}));

// Mock next/navigation
const pushMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

describe('ModelOrchestrationPlaybookCard', () => {
  it('renders summary card with title, badge and action buttons', () => {
    render(<ModelOrchestrationPlaybookCard />);

    expect(screen.getByText('Model Orchestration Playbook')).toBeDefined();
    expect(screen.getByText('Playbook')).toBeDefined();
    expect(screen.getByText('View Playbook')).toBeDefined();
  });

  it('toggles mini preview when expand button is clicked', () => {
    render(<ModelOrchestrationPlaybookCard />);

    // Initially collapsed
    expect(screen.queryByText('High reasoning planner + fast tool executor.')).toBeNull();

    // Click expand
    const expandBtn = screen.getByLabelText('Expand');
    fireEvent.click(expandBtn);

    // Now expanded
    expect(screen.getByText('High reasoning planner + fast tool executor.')).toBeDefined();
    expect(screen.getByText('3-Tier Adaptive Routing')).toBeDefined();
    expect(screen.getByText('MoA Consensus Overlay')).toBeDefined();

    // Click collapse
    const collapseBtn = screen.getByLabelText('Collapse');
    fireEvent.click(collapseBtn);
    expect(screen.queryByText('High reasoning planner + fast tool executor.')).toBeNull();
  });

  it('opens full dialog when viewFullPlaybook button is clicked', () => {
    render(<ModelOrchestrationPlaybookCard />);

    const viewBtn = screen.getByText('View Playbook');
    fireEvent.click(viewBtn);

    // Dialog content should now be visible
    expect(screen.getAllByText('Model Orchestration Playbook & Best Practices').length).toBeGreaterThan(0);
    expect(screen.getByText('1. Brain vs. Hands Dispatch')).toBeDefined();
    expect(screen.getByText('Routing vs. MoA')).toBeDefined();

    // Click configure button
    const configBtn = screen.getByText('Configure in Settings');
    fireEvent.click(configBtn);
    expect(pushMock).toHaveBeenCalledWith('/settings/models#smart-routing');
  });
});
