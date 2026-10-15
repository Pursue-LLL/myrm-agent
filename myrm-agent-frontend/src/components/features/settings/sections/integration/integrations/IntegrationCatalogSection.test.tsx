import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ButtonHTMLAttributes } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import useConfigStore from '@/store/useConfigStore';
import type { MCPServiceConfig } from '@/store/config/types';
import IntegrationCatalogSection from './IntegrationCatalogSection';
import type { CatalogEntry, CatalogResponse } from './catalog-types';

const mockApiRequest = vi.hoisted(() => vi.fn());
const mockListAgents = vi.hoisted(() => vi.fn());
const mockListWebhooks = vi.hoisted(() => vi.fn());

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) =>
    Object.assign((key: string, values?: { name: string }) => `${namespace}.${key}${values ? `:${values.name}` : ''}`, {
      has: (key: string) => !key.endsWith('.unlisted'),
    }),
  useLocale: () => 'en',
}));

vi.mock('@/services/agent', () => ({
  listAgents: (...args: unknown[]) => mockListAgents(...args),
}));

vi.mock('@/services/lifecycleWebhook', () => ({
  listLifecycleWebhooks: (...args: unknown[]) => mockListWebhooks(...args),
  createLifecycleWebhook: vi.fn(),
  updateLifecycleWebhook: vi.fn(),
  deleteLifecycleWebhook: vi.fn(),
  pingSavedLifecycleWebhook: vi.fn(),
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

function makeCatalogEntry(id: string, name: string, overrides: Partial<CatalogEntry> = {}): CatalogEntry {
  return {
    id,
    name,
    nameZh: `${name}_zh`,
    description: `${name} description`,
    descriptionZh: `${name} 描述`,
    icon: id,
    category: 'productivity',
    connectorType: 'mcp',
    authType: 'none',
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
    ...overrides,
  };
}

const MOCK_CATALOG: CatalogResponse = {
  entries: [
    makeCatalogEntry('microsoft-todo', 'Microsoft To Do', {
      nameZh: '微软待办',
      description: 'Manage your Microsoft To Do lists, tasks, and checklist items',
      descriptionZh: '通过你的 Microsoft 账户管理 Microsoft To Do 清单、任务和子任务',
      tags: ['tasks', 'todo', 'microsoft', '365', 'checklist', '待办', '微软'],
    }),
    makeCatalogEntry('notion', 'Notion', { tags: ['wiki', 'notes'], website: 'https://notion.so' }),
    makeCatalogEntry('dingtalk', 'DingTalk', {
      nameZh: '钉钉',
      tags: ['messaging', '钉钉', '通讯录', '待办'],
    }),
  ],
  categories: ['productivity'],
  total: 3,
};

function makeSavedService(name: string, enabled = true): MCPServiceConfig {
  return { name, type: 'stdio', description: '', enabled };
}

describe('IntegrationCatalogSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useConfigStore.setState({ mcpConfigs: [] });
    mockListAgents.mockResolvedValue({ items: [], total: 0 });
    mockListWebhooks.mockResolvedValue([]);
    mockApiRequest.mockImplementation((url: string) => {
      if (url === '/integrations/catalog') {
        return Promise.resolve(MOCK_CATALOG);
      }
      if (url === '/lifecycle-webhooks') {
        return Promise.resolve([]);
      }
      return Promise.resolve({});
    });
    mockListAgents.mockResolvedValue({ items: [], total: 0 });
    mockListWebhooks.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders catalog cards after loading', async () => {
    render(<IntegrationCatalogSection />);

    await waitFor(() => {
      expect(screen.getByText('Microsoft To Do')).toBeInTheDocument();
    });
    expect(screen.getByText('Notion')).toBeInTheDocument();
    expect(mockApiRequest).toHaveBeenCalledWith('/integrations/catalog', { silent: true });
  });

  it('filters by Chinese tag 待办 and surfaces microsoft-todo', async () => {
    render(<IntegrationCatalogSection />);

    await waitFor(() => {
      expect(screen.getByText('Microsoft To Do')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText('settings.integrationCatalog.searchPlaceholder'), {
      target: { value: '待办' },
    });

    await waitFor(() => {
      expect(screen.getByText('Microsoft To Do')).toBeInTheDocument();
      expect(screen.getByText('DingTalk')).toBeInTheDocument();
      expect(screen.queryByText('Notion')).not.toBeInTheDocument();
    });
  });

  it('filters by official Chinese name 微软待办', async () => {
    render(<IntegrationCatalogSection />);

    await waitFor(() => {
      expect(screen.getByText('Microsoft To Do')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText('settings.integrationCatalog.searchPlaceholder'), {
      target: { value: '微软待办' },
    });

    await waitFor(() => {
      expect(screen.getByText('Microsoft To Do')).toBeInTheDocument();
      expect(screen.queryByText('Notion')).not.toBeInTheDocument();
      expect(screen.queryByText('DingTalk')).not.toBeInTheDocument();
    });
  });

  it('shows noResults for an unknown query', async () => {
    render(<IntegrationCatalogSection />);

    await waitFor(() => {
      expect(screen.getByText('Microsoft To Do')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText('settings.integrationCatalog.searchPlaceholder'), {
      target: { value: 'xyznonexistent' },
    });

    await waitFor(() => {
      expect(screen.getByText('settings.integrationCatalog.noResults')).toBeInTheDocument();
    });
  });

  it('opens connect dialog when a card is clicked', async () => {
    render(<IntegrationCatalogSection />);

    await waitFor(() => {
      expect(screen.getByText('Microsoft To Do')).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText('settings.integrationCatalog.connect')[0]);

    expect(screen.getByTestId('connect-dialog')).toBeInTheDocument();
  });

  it('closes the connect dialog once the connection is confirmed', async () => {
    render(<IntegrationCatalogSection />);

    await waitFor(() => {
      expect(screen.getByText('Microsoft To Do')).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText('settings.integrationCatalog.connect')[0]);
    fireEvent.click(screen.getByText('confirm-connect'));

    expect(screen.queryByTestId('connect-dialog')).not.toBeInTheDocument();
  });

  it('offers manage instead of connect for services the user already holds', async () => {
    useConfigStore.setState({
      mcpConfigs: [makeSavedService('notion'), makeSavedService('dingtalk', false)],
    });
    render(<IntegrationCatalogSection />);

    await waitFor(() => {
      expect(screen.getByText('Microsoft To Do')).toBeInTheDocument();
    });

    expect(screen.getAllByText('settings.integrationCatalog.connect')).toHaveLength(1);
    expect(screen.getByText('settings.integrationCatalog.connected')).toBeInTheDocument();
    expect(screen.getByText('settings.integrationCatalog.disabled')).toBeInTheDocument();
    const manageLinks = screen.getAllByRole('link', { name: 'settings.integrationCatalog.manage' });
    expect(manageLinks).toHaveLength(2);
    manageLinks.forEach((link) => expect(link).toHaveAttribute('href', '/settings/mcp'));
  });

  it('turns a card into connected as soon as the service is saved', async () => {
    render(<IntegrationCatalogSection />);

    await waitFor(() => {
      expect(screen.getByText('Notion')).toBeInTheDocument();
    });
    expect(screen.queryByText('settings.integrationCatalog.connected')).not.toBeInTheDocument();

    useConfigStore.setState({ mcpConfigs: [makeSavedService('notion')] });

    await waitFor(() => {
      expect(screen.getByText('settings.integrationCatalog.connected')).toBeInTheDocument();
    });
    expect(screen.getAllByText('settings.integrationCatalog.connect')).toHaveLength(2);
  });

  it('exposes the vendor website as a named link that stays visible on touch screens', async () => {
    render(<IntegrationCatalogSection />);

    await waitFor(() => {
      expect(screen.getByText('Notion')).toBeInTheDocument();
    });

    const link = screen.getByRole('link', { name: 'settings.integrationCatalog.openWebsite:Notion' });
    expect(link).toHaveAttribute('href', 'https://notion.so');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link).not.toHaveClass('opacity-0');
  });

  it('labels categories through i18n and falls back to the raw id for unlisted ones', async () => {
    mockApiRequest.mockImplementation((url: string) =>
      Promise.resolve(
        url === '/integrations/catalog' ? { ...MOCK_CATALOG, categories: ['productivity', 'unlisted'] } : {},
      ),
    );
    render(<IntegrationCatalogSection />);

    await waitFor(() => {
      expect(screen.getByText('settings.integrationCatalog.categories.productivity')).toBeInTheDocument();
    });
    expect(screen.getByText('unlisted')).toBeInTheDocument();
  });
});
