/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'zh',
}));

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

const mockToast = vi.fn();
vi.mock('@/hooks/shared/useToast', () => ({
  toast: (args: unknown) => mockToast(args),
}));

const chatStoreMock = vi.hoisted(() => ({
  agentConfig: null as Record<string, unknown> | null,
  setAgentConfig: vi.fn(),
  actionMode: 'agent' as string,
  toggleConfigPanel: vi.fn(),
  loading: false,
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: typeof chatStoreMock) => unknown) => selector(chatStoreMock),
}));

const mockFetchAgent = vi.fn();
vi.mock('@/store/useAgentStore', () => ({
  default: {
    getState: () => ({
      fetchAgent: mockFetchAgent,
    }),
  },
}));

const mockUseAgentGallery = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/agent/useAgentGallery', () => ({
  useAgentGallery: (options: unknown) => mockUseAgentGallery(options),
}));

vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/primitives/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div data-testid="dropdown-menu">{children}</div>,
  DropdownMenuTrigger: ({
    children,
    disabled,
  }: {
    children: React.ReactElement<{ disabled?: boolean }>;
    disabled?: boolean;
  }) => (
    <div data-testid="dropdown-trigger" aria-disabled={disabled}>
      {children}
    </div>
  ),
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="dropdown-content">{children}</div>
  ),
  DropdownMenuLabel: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="dropdown-label">{children}</div>
  ),
  DropdownMenuSeparator: () => <hr data-testid="dropdown-separator" />,
  DropdownMenuItem: ({
    children,
    onClick,
    className,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    className?: string;
  }) => (
    <button type="button" onClick={onClick} className={className} data-testid="dropdown-item">
      {children}
    </button>
  ),
}));

import AgentIndicator from '../AgentIndicator';

describe('AgentIndicator Component', () => {
  const dummyPresets = [
    {
      id: 'coder-preset',
      name: '代码专家',
      description: '全栈编程助手',
      icon: 'Code',
      skillIds: ['code_edit'],
      systemPrompt: 'You are an expert coder.',
    },
    {
      id: 'search-preset',
      name: '调研专家',
      description: '深度搜索与分析',
      icon: 'Search',
      skillIds: ['deep_search'],
      systemPrompt: 'You are an expert researcher.',
    },
  ];

  const dummyCustomAgents = [
    {
      id: 'custom-finance',
      name: '财务顾问',
      description: '财务分析与报表',
      avatar_url: 'gradient:2',
      skill_ids: ['calc_sheet'],
      mcp_ids: ['finance_mcp'],
      system_prompt: 'You are a financial advisor.',
    },
    {
      id: 'custom-emoji',
      name: '表情专家',
      description: '带emoji头像的智能体',
      avatar_url: 'emoji:🚀',
      skill_ids: [],
    },
    {
      id: 'custom-img',
      name: '视觉设计',
      description: '带图片头像的智能体',
      avatar_url: 'image:https://example.com/avatar.png',
      skill_ids: [],
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    chatStoreMock.agentConfig = null;
    chatStoreMock.actionMode = 'agent';
    chatStoreMock.loading = false;

    mockUseAgentGallery.mockImplementation(({ onSelectPreset, onSelectCustomAgent }) => ({
      presetAgents: dummyPresets,
      customAgents: dummyCustomAgents,
      handlePresetClick: (preset: (typeof dummyPresets)[0]) => onSelectPreset(preset),
      handleCustomAgentClick: (agent: (typeof dummyCustomAgents)[0]) => onSelectCustomAgent(agent),
    }));
  });

  it('renders nothing when actionMode is not agent (e.g. fast mode)', () => {
    chatStoreMock.actionMode = 'fast';
    const { container } = render(<AgentIndicator />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders default icon and trigger button in agent mode without active config', () => {
    render(<AgentIndicator />);
    const trigger = screen.getByTestId('dropdown-trigger');
    expect(trigger).toBeInTheDocument();
    expect(screen.getByTestId('dropdown-menu')).toBeInTheDocument();
  });

  it('disables the dropdown trigger button when loading is true', () => {
    chatStoreMock.loading = true;
    render(<AgentIndicator />);
    const trigger = screen.getByTestId('dropdown-trigger');
    expect(trigger).toHaveAttribute('aria-disabled', 'true');
  });

  it('renders active preset agent details when agentConfig is set', () => {
    chatStoreMock.agentConfig = {
      presetId: 'coder-preset',
      presetName: '代码专家',
      presetIcon: 'Code',
      selectedSkillIds: ['code_edit'],
    };
    render(<AgentIndicator />);
    const matchingElements = screen.getAllByText('代码专家');
    expect(matchingElements.length).toBeGreaterThanOrEqual(1);
    expect(matchingElements[0]).toBeInTheDocument();
  });

  it('renders custom agent avatar variants (gradient, emoji, image) cleanly without crashing', () => {
    // 1. Emoji avatar
    chatStoreMock.agentConfig = {
      agentId: 'custom-emoji',
      agentName: '表情专家',
      avatarUrl: 'emoji:🚀',
    };
    const { rerender } = render(<AgentIndicator />);
    expect(screen.getAllByText('表情专家')[0]).toBeInTheDocument();

    // 2. Image avatar
    chatStoreMock.agentConfig = {
      agentId: 'custom-img',
      agentName: '视觉设计',
      avatarUrl: 'image:https://example.com/avatar.png',
    };
    rerender(<AgentIndicator />);
    expect(screen.getAllByText('视觉设计')[0]).toBeInTheDocument();
  });

  it('switches preset agent when preset item is clicked', async () => {
    mockFetchAgent.mockResolvedValueOnce(null);
    render(<AgentIndicator />);

    const presetItems = screen.getAllByText('代码专家');
    fireEvent.click(presetItems[presetItems.length - 1]);

    await waitFor(() => {
      expect(chatStoreMock.setAgentConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          agentId: 'coder-preset',
          presetId: 'coder-preset',
          presetName: '代码专家',
          selectedSkillIds: ['code_edit'],
        }),
      );
      expect(mockToast).toHaveBeenCalledWith({
        title: 'switchSuccess',
        description: '代码专家',
      });
    });
  });

  it('switches custom agent when custom agent item is clicked', async () => {
    mockFetchAgent.mockResolvedValueOnce(null);
    render(<AgentIndicator />);

    const customAgentItem = screen.getByText('财务顾问');
    fireEvent.click(customAgentItem);

    await waitFor(() => {
      expect(chatStoreMock.setAgentConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          agentId: 'custom-finance',
          agentName: '财务顾问',
          selectedSkillIds: ['calc_sheet'],
          selectedMcpNames: ['finance_mcp'],
        }),
      );
      expect(mockToast).toHaveBeenCalledWith({
        title: 'switchSuccess',
        description: '财务顾问',
      });
    });
  });

  it('handles empty agent list gracefully', () => {
    mockUseAgentGallery.mockReturnValueOnce({
      presetAgents: [],
      customAgents: [],
      handlePresetClick: vi.fn(),
      handleCustomAgentClick: vi.fn(),
    });

    render(<AgentIndicator />);
    expect(screen.getByTestId('dropdown-content')).toBeInTheDocument();
    expect(screen.getByText('openConfigPanel')).toBeInTheDocument();
  });

  it('triggers toggleConfigPanel when configuration entry is clicked', () => {
    render(<AgentIndicator />);
    const configItem = screen.getByText('openConfigPanel');
    fireEvent.click(configItem);
    expect(chatStoreMock.toggleConfigPanel).toHaveBeenCalledTimes(1);
  });

  it('navigates to settings/agents when manageAgents entry is clicked', () => {
    render(<AgentIndicator />);
    const manageItem = screen.getByText('manageAgents');
    fireEvent.click(manageItem);
    expect(mockPush).toHaveBeenCalledWith('/settings/agents');
  });
});
