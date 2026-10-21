import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ButtonHTMLAttributes } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import useConfigStore from '@/store/useConfigStore';
import type { MCPServiceConfig } from '@/store/config/types';
import ToolsConnectOnboardingStep from '../ToolsConnectOnboardingStep';
import type {
  CatalogEntry,
  CatalogResponse,
} from '@/components/features/settings/sections/integration/integrations/catalog-types';

const mockApiRequest = vi.hoisted(() => vi.fn());
const uiLocale = vi.hoisted(() => ({ current: 'en' }));

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
  useLocale: () => uiLocale.current,
}));

vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => mockApiRequest(...args),
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, onClick, ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" onClick={onClick} {...rest}>
      {children}
    </button>
  ),
}));

vi.mock('@/components/primitives/skeleton', () => ({
  Skeleton: ({ className }: { className?: string }) => <div data-testid="skeleton" className={className} />,
}));

// The real dialog saves the service into the config store before reporting the connection.
vi.mock('@/components/features/settings/sections/integration/integrations/IntegrationConnectDialog', () => ({
  IntegrationConnectDialog: ({
    entry,
    locale,
    onClose,
    onConnected,
  }: {
    entry: CatalogEntry;
    locale: string;
    onClose: () => void;
    onConnected: () => void;
  }) => (
    <div data-testid="connect-dialog" data-locale={locale}>
      <span>{entry.name}</span>
      <button
        type="button"
        onClick={() => {
          useConfigStore.setState({ mcpConfigs: [makeSavedService(String(entry.mcpConfig?.name))] });
          onConnected();
        }}
      >
        confirm-connect
      </button>
      <button type="button" onClick={onClose}>
        close-dialog
      </button>
    </div>
  ),
}));

vi.mock('@/components/features/settings/sections/integration/integrations/service-icons', () => ({
  SERVICE_ICONS: {},
}));

function makeSavedService(name: string, enabled = true): MCPServiceConfig {
  return { name, type: 'stdio', description: '', enabled };
}

function makeCatalogEntry(id: string, name: string): CatalogEntry {
  return {
    id,
    name,
    nameZh: `${name}_zh`,
    description: `${name} description`,
    descriptionZh: `${name} 描述`,
    icon: id,
    category: 'development',
    connectorType: 'mcp',
    authType: 'api_key',
    helpUrl: null,
    helpText: null,
    helpTextZh: null,
    envKey: null,
    credentialFields: null,
    tags: [],
    website: null,
    mcpConfig: { name: id },
    deploymentScope: 'all_modes',
    postConnectGuide: null,
    postConnectGuideZh: null,
  };
}

const MOCK_CATALOG: CatalogResponse = {
  entries: [
    makeCatalogEntry('github', 'GitHub'),
    makeCatalogEntry('notion', 'Notion'),
    makeCatalogEntry('microsoft-todo', 'Microsoft To Do'),
    makeCatalogEntry('slack', 'Slack'),
    makeCatalogEntry('linear', 'Linear'),
  ],
  categories: ['development', 'productivity'],
  total: 5,
};

describe('ToolsConnectOnboardingStep', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    uiLocale.current = 'en';
    useConfigStore.setState({ mcpConfigs: [] });
    mockApiRequest.mockResolvedValue(MOCK_CATALOG);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders featured services after loading', async () => {
    const onComplete = vi.fn();
    const onSkip = vi.fn();

    render(<ToolsConnectOnboardingStep onComplete={onComplete} onSkip={onSkip} />);

    await waitFor(() => {
      expect(screen.getByText('GitHub')).toBeInTheDocument();
    });
    expect(screen.getByText('Notion')).toBeInTheDocument();
    expect(screen.getByText('Slack')).toBeInTheDocument();
    expect(screen.getByText('Linear')).toBeInTheDocument();
  });

  it('calls onSkip when catalog fetch fails', async () => {
    mockApiRequest.mockRejectedValue(new Error('network'));
    const onSkip = vi.fn();

    render(<ToolsConnectOnboardingStep onComplete={vi.fn()} onSkip={onSkip} />);

    await waitFor(() => {
      expect(onSkip).toHaveBeenCalledTimes(1);
    });
  });

  it('opens connect dialog when service is clicked', async () => {
    render(<ToolsConnectOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('GitHub')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('GitHub'));

    expect(screen.getByTestId('connect-dialog')).toBeInTheDocument();
  });

  it('marks service as connected after dialog confirms', async () => {
    const onComplete = vi.fn();
    render(<ToolsConnectOnboardingStep onComplete={onComplete} onSkip={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('GitHub')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('GitHub'));
    fireEvent.click(screen.getByText('confirm-connect'));

    await waitFor(() => {
      expect(screen.getByText('settings.integrationCatalog.connected')).toBeInTheDocument();
    });

    expect(screen.getByText('boot.onboarding.toolsConnect.continueButton')).toBeInTheDocument();
    expect(screen.queryByTestId('connect-dialog')).not.toBeInTheDocument();
  });

  it('skip button calls onSkip directly', async () => {
    const onSkip = vi.fn();
    render(<ToolsConnectOnboardingStep onComplete={vi.fn()} onSkip={onSkip} />);

    await waitFor(() => {
      expect(screen.getByText('GitHub')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('boot.onboarding.toolsConnect.skipButton'));
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it('continue button appears only after connecting at least one service', async () => {
    render(<ToolsConnectOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('GitHub')).toBeInTheDocument();
    });

    expect(screen.queryByText('boot.onboarding.toolsConnect.continueButton')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('GitHub'));
    fireEvent.click(screen.getByText('confirm-connect'));

    await waitFor(() => {
      expect(screen.getByText('boot.onboarding.toolsConnect.continueButton')).toBeInTheDocument();
    });
  });

  it('shows a service connected earlier as connected and lets the user continue right away', async () => {
    useConfigStore.setState({ mcpConfigs: [makeSavedService('github')] });
    render(<ToolsConnectOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('GitHub')).toBeInTheDocument();
    });

    expect(screen.getByText('settings.integrationCatalog.connected')).toBeInTheDocument();
    expect(screen.getByText('boot.onboarding.toolsConnect.continueButton')).toBeInTheDocument();
    fireEvent.click(screen.getByText('GitHub'));
    expect(screen.queryByTestId('connect-dialog')).not.toBeInTheDocument();
  });

  it('does not count a switched-off service as connected', async () => {
    useConfigStore.setState({ mcpConfigs: [makeSavedService('github', false)] });
    render(<ToolsConnectOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('GitHub')).toBeInTheDocument();
    });

    expect(screen.getByText('settings.integrationCatalog.disabled')).toBeInTheDocument();
    expect(screen.queryByText('settings.integrationCatalog.connected')).not.toBeInTheDocument();
    expect(screen.queryByText('boot.onboarding.toolsConnect.continueButton')).not.toBeInTheDocument();
  });

  it('shows Chinese copy and passes the Chinese catalog locale to the dialog for every zh variant', async () => {
    uiLocale.current = 'zh-TW';
    render(<ToolsConnectOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('GitHub_zh')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('GitHub_zh'));

    expect(screen.getByTestId('connect-dialog')).toHaveAttribute('data-locale', 'zh');
  });
});
