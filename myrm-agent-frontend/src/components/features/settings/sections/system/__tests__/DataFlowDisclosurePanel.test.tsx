import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DataFlowDisclosurePanel } from '../DataFlowDisclosurePanel';
import useProviderStore from '@/store/useProviderStore';
import useConfigStore from '@/store/useConfigStore';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('../SettingsSection', () => ({
  default: ({ title, description, children }: { title: string; description: string; children: React.ReactNode }) => (
    <div data-testid="settings-section">
      <h3>{title}</h3>
      <p>{description}</p>
      {children}
    </div>
  ),
}));

describe('DataFlowDisclosurePanel', () => {
  it('renders local private domain components properly', () => {
    useProviderStore.setState({
      providers: [],
    });
    useConfigStore.setState({
      mcpConfigs: [],
    });

    render(<DataFlowDisclosurePanel />);

    expect(screen.getByText('localDomain')).toBeDefined();
    expect(screen.getByText('localChatHistory')).toBeDefined();
    expect(screen.getByText('localMemory')).toBeDefined();
    expect(screen.getByText('localWorkspace')).toBeDefined();
    expect(screen.getByText('localCredentials')).toBeDefined();
    expect(screen.getByText('noEgress')).toBeDefined();
  });

  it('renders active providers and mcp servers dynamically in egress section', () => {
    useProviderStore.setState({
      providers: [
        {
          id: 'anthropic',
          name: 'Anthropic Claude',
          apiUrl: 'https://api.anthropic.com',
          apiKey: 'sk-ant-test',
          isEnabled: true,
          models: [],
        },
      ],
    });
    useConfigStore.setState({
      mcpConfigs: [
        {
          name: 'filesystem-server',
          enabled: true,
          type: 'stdio',
          command: 'npx -y @modelcontextprotocol/server-filesystem',
        },
      ],
    });

    render(<DataFlowDisclosurePanel />);

    expect(screen.getByText('Anthropic Claude')).toBeDefined();
    expect(screen.getByText('filesystem-server')).toBeDefined();
    expect(screen.getByText('https://api.anthropic.com')).toBeDefined();
    expect(screen.getByText('npx -y @modelcontextprotocol/server-filesystem')).toBeDefined();
  });
});
