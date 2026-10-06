import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { AgentReadinessItem } from '@/services/agent';

import AgentReadinessList from '../AgentReadinessList';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

function item(overrides: Partial<AgentReadinessItem> = {}): AgentReadinessItem {
  return {
    dimension: 'model',
    level: 'blocked',
    reason: 'No default model is configured',
    next_action: 'Configure a model',
    settings_path: '/settings/models',
    ...overrides,
  };
}

describe('AgentReadinessList', () => {
  it('names each known dimension and shows the reason', () => {
    render(
      <AgentReadinessList items={[item(), item({ dimension: 'mcp', level: 'warning', reason: 'Server is off' })]} />,
    );

    expect(screen.getByText('Agent.readiness.dimensions.model')).toBeInTheDocument();
    expect(screen.getByText('Agent.readiness.dimensions.mcp')).toBeInTheDocument();
    expect(screen.getByText('No default model is configured')).toBeInTheDocument();
    expect(screen.getByText('Server is off')).toBeInTheDocument();
  });

  it('shows an unknown dimension verbatim instead of inventing a label', () => {
    render(<AgentReadinessList items={[item({ dimension: 'future-dimension' })]} />);

    expect(screen.getByText('future-dimension')).toBeInTheDocument();
  });

  it('links to the fix only when asked to and only for items that need attention', () => {
    const { rerender } = render(<AgentReadinessList items={[item()]} />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();

    rerender(
      <AgentReadinessList
        items={[item(), item({ dimension: 'skills', level: 'ready', settings_path: '/s' })]}
        withLinks
      />,
    );
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', '/settings/models');
  });

  it('does not link an item without a settings path', () => {
    render(<AgentReadinessList items={[item({ settings_path: '' })]} withLinks />);

    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
