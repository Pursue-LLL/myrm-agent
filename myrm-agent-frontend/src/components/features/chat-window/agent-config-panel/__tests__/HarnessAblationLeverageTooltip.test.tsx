/**
 * @vitest-environment jsdom
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HarnessAblationLeverageTooltip } from '../HarnessAblationLeverageTooltip';

// Mock next-intl
const translations: Record<string, string> = {
  title: 'Harness Leverage Guide',
  badge: 'AHE Empirical Finding',
  expand: 'Expand Guide',
  collapse: 'Collapse',
  description: 'Empirical ablation ranking',
  toolTier: 'Tools / Skills',
  middlewareTier: 'Middleware Guardrails',
  memoryTier: 'Memory Retrieval',
  promptTier: 'Prompt-only',
  cacheTip: 'Prefer configuring tools and middleware over endlessly expanding system prompts.',
};
const stableT = (key: string) => translations[key] || key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('HarnessAblationLeverageTooltip', () => {
  it('renders collapsed by default and expands on click', () => {
    render(<HarnessAblationLeverageTooltip />);

    expect(screen.getByText('Harness Leverage Guide')).toBeDefined();
    expect(screen.getByText('AHE Empirical Finding')).toBeDefined();
    expect(screen.queryByText('Tools / Skills')).toBeNull();

    // Click expand
    const expandBtn = screen.getByRole('button', { name: /Expand Guide/i });
    fireEvent.click(expandBtn);

    expect(screen.getByText('Tools / Skills')).toBeDefined();
    expect(screen.getByText('Middleware Guardrails')).toBeDefined();
    expect(screen.getByText('Memory Retrieval')).toBeDefined();
    expect(screen.getByText('Prompt-only')).toBeDefined();

    // Click collapse
    const collapseBtn = screen.getByRole('button', { name: /Collapse/i });
    fireEvent.click(collapseBtn);

    expect(screen.queryByText('Tools / Skills')).toBeNull();
  });
});
