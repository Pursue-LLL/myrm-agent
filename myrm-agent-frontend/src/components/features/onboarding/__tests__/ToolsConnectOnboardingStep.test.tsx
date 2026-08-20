import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ButtonHTMLAttributes } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ToolsConnectOnboardingStep from '../ToolsConnectOnboardingStep';
import type {
  CatalogEntry,
  CatalogResponse,
} from '@/components/features/settings/sections/integration/integrations/catalog-types';

const mockApiRequest = vi.hoisted(() => vi.fn());

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
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

vi.mock('@/components/features/settings/sections/integration/integrations/IntegrationConnectDialog', () => ({
  IntegrationConnectDialog: ({
    entry,
    onClose,
    onConnected,
  }: {
    entry: CatalogEntry;
    onClose: () => void;
    onConnected: () => void;
  }) => (
    <div data-testid="connect-dialog">
      <span>{entry.name}</span>
      <button type="button" onClick={onConnected}>
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
    mcpConfig: null,
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
      expect(screen.getByText('boot.onboarding.toolsConnect.connected')).toBeInTheDocument();
    });

    expect(screen.getByText('boot.onboarding.toolsConnect.continueButton')).toBeInTheDocument();
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
});
