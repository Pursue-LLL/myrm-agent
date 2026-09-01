import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ButtonHTMLAttributes } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import IntegrationCatalogSection from './IntegrationCatalogSection';
import type { CatalogEntry, CatalogResponse } from './catalog-types';

const mockApiRequest = vi.hoisted(() => vi.fn());
const mockListAgents = vi.hoisted(() => vi.fn());
const mockListWebhooks = vi.hoisted(() => vi.fn());

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
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
    mcpConfig: null,
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
    makeCatalogEntry('notion', 'Notion', { tags: ['wiki', 'notes'] }),
    makeCatalogEntry('dingtalk', 'DingTalk', {
      nameZh: '钉钉',
      tags: ['messaging', '钉钉', '通讯录', '待办'],
    }),
  ],
  categories: ['productivity'],
  total: 3,
};

describe('IntegrationCatalogSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
});
