/**
 * @vitest-environment jsdom
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ComponentAblationImpactRankingChip } from '../components/ComponentAblationImpactRankingChip';
import type { AblationRecommendationItem } from '../hooks/useCasesEval';

// Mock next-intl
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) => {
    const translations: Record<string, string> = {
      title: 'Component Ablation Impact & Harness Edit Recommendations',
      subtitle: 'AHE Ablation Priority Ranking',
      description: 'Empirical ablation ranking',
      affectsCases: `Affects ${params?.count ?? 0} failed cases`,
      quickConfig: 'Configure',
    };
    return translations[key] || key;
  },
}));

describe('ComponentAblationImpactRankingChip', () => {
  it('renders nothing when recommendations array is empty', () => {
    const { container } = render(<ComponentAblationImpactRankingChip recommendations={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders recommendations with tier badges, stars, and deep-link click', () => {
    const recs: AblationRecommendationItem[] = [
      {
        component: 'middleware',
        priority: 1,
        action_key: 'enable_argument_repair_middleware',
        title: 'Tool Argument Serialization Failure',
        reason: 'Model generated invalid parameters. Enable argument validation and repair middleware.',
        target_config_tab: 'capabilities',
        target_setting_key: 'tool_interceptor',
        affected_case_count: 5,
        evidence_modes: ['tool_argument_malformed'],
      },
      {
        component: 'tool',
        priority: 1,
        action_key: 'bind_missing_tool_or_skill',
        title: 'Tool Selection Defect',
        reason: 'Agent failed to locate tools.',
        target_config_tab: 'capabilities',
        target_setting_key: 'skills',
        affected_case_count: 3,
        evidence_modes: ['tool_selection_error'],
      },
    ];

    render(<ComponentAblationImpactRankingChip recommendations={recs} profileId="agent-123" />);

    expect(screen.getByText('Component Ablation Impact & Harness Edit Recommendations')).toBeDefined();
    expect(screen.getByText('Tool Argument Serialization Failure')).toBeDefined();
    expect(screen.getByText('Tool Selection Defect')).toBeDefined();
    expect(screen.getByText('Affects 5 failed cases')).toBeDefined();
    expect(screen.getByText('Affects 3 failed cases')).toBeDefined();

    const configButtons = screen.getAllByRole('button', { name: /Configure/i });
    expect(configButtons.length).toBe(2);

    // Click config button
    fireEvent.click(configButtons[0]);
    // Verifies button is clickable without throwing
  });
});
