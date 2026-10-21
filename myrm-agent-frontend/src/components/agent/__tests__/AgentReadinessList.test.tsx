import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { AgentReadinessItem } from '@/services/agent';

import AgentReadinessList from '../AgentReadinessList';

const MESSAGES: Record<string, string> = {
  'dimensions.model': 'Model',
  'dimensions.mcp': 'MCP servers',
  'dimensions.skills': 'Skills',
  'dimensions.other': 'Other',
  'reasons.model_not_ready': 'No model is ready yet',
  'reasons.mcp_not_enabled': 'Switched off: {names}',
  'reasons.mcp_missing_secrets': 'Missing credentials: {names}',
  'reasons.skills_missing': '{count} skill(s) missing',
  'fallback.ready': 'All set',
  'fallback.warning': 'This may limit the agent',
  'fallback.blocked': 'This needs attention',
  fix: 'Fix',
};

function interpolate(text: string, values?: Record<string, unknown>): string {
  return Object.entries(values ?? {}).reduce((acc, [name, value]) => acc.replaceAll(`{${name}}`, String(value)), text);
}

vi.mock('next-intl', () => ({
  useTranslations: () =>
    Object.assign((key: string, values?: Record<string, unknown>) => interpolate(MESSAGES[key] ?? key, values), {
      has: (key: string) => key in MESSAGES,
    }),
}));

function item(overrides: Partial<AgentReadinessItem> = {}): AgentReadinessItem {
  return {
    dimension: 'model',
    level: 'blocked',
    code: 'model_not_ready',
    reason: 'No default model is configured',
    next_action: 'Configure a model',
    settings_path: '/settings/models',
    names: [],
    count: 0,
    ...overrides,
  };
}

describe('AgentReadinessList', () => {
  it('names each dimension and says what is wrong in localized words, never the backend English', () => {
    render(
      <AgentReadinessList
        items={[
          item(),
          item({ dimension: 'mcp', level: 'warning', code: 'mcp_not_enabled', names: ['slack', 'github'], count: 2 }),
          item({ dimension: 'skills', level: 'warning', code: 'skills_missing', count: 3 }),
        ]}
      />,
    );

    expect(screen.getByText('Model')).toBeInTheDocument();
    expect(screen.getByText('MCP servers')).toBeInTheDocument();
    expect(screen.getByText('No model is ready yet')).toBeInTheDocument();
    expect(screen.getByText('Switched off: slack, github')).toBeInTheDocument();
    expect(screen.getByText('3 skill(s) missing')).toBeInTheDocument();
    expect(screen.queryByText('No default model is configured')).not.toBeInTheDocument();
  });

  it('shows several findings of one dimension as separate rows with distinct keys', () => {
    // React reports colliding list keys through console.error.
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <AgentReadinessList
        items={[
          item({ dimension: 'mcp', level: 'warning', code: 'mcp_not_enabled', names: ['slack'], count: 1 }),
          item({ dimension: 'mcp', level: 'warning', code: 'mcp_missing_secrets', names: ['SLACK_TOKEN'], count: 1 }),
        ]}
      />,
    );

    expect(screen.getAllByText('MCP servers')).toHaveLength(2);
    expect(screen.getByText('Switched off: slack')).toBeInTheDocument();
    expect(screen.getByText('Missing credentials: SLACK_TOKEN')).toBeInTheDocument();
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it('names only the first few servers or keys of a long finding and signals there are more', () => {
    const names = ['alpha', 'beta', 'gamma', 'delta', 'epsilon'];
    render(
      <AgentReadinessList
        items={[
          item({ dimension: 'mcp', level: 'warning', code: 'mcp_not_enabled', names, count: names.length }),
          item({ dimension: 'mcp', level: 'warning', code: 'mcp_missing_secrets', names: names.slice(0, 3), count: 3 }),
        ]}
      />,
    );

    expect(screen.getByText('Switched off: alpha, beta, gamma…')).toBeInTheDocument();
    expect(screen.getByText('Missing credentials: alpha, beta, gamma')).toBeInTheDocument();
    expect(screen.queryByText(/delta/)).not.toBeInTheDocument();
  });

  it('falls back to a generic line per level for a finding this build does not know', () => {
    render(
      <AgentReadinessList
        items={[
          item({ code: 'something_new', level: 'warning' }),
          item({ dimension: 'skills', code: 'something_newer', level: 'blocked' }),
        ]}
      />,
    );

    expect(screen.getByText('This may limit the agent')).toBeInTheDocument();
    expect(screen.getByText('This needs attention')).toBeInTheDocument();
    expect(screen.queryByText('No default model is configured')).not.toBeInTheDocument();
  });

  it('labels an unknown dimension generically instead of printing the backend token', () => {
    render(<AgentReadinessList items={[item({ dimension: 'future-dimension' })]} />);

    expect(screen.getByText('Other')).toBeInTheDocument();
    expect(screen.queryByText('future-dimension')).not.toBeInTheDocument();
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
