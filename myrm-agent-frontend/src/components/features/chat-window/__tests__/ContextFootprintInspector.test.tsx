import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ContextFootprintInspector, { formatTokenNumber } from '../ContextFootprintInspector';
import type { MCPServiceConfig } from '@/store/config/types';

const toggleMCPConfigMock = vi.fn();
let mockMcpConfigs: MCPServiceConfig[] = [];
let mockSystemInstructions = '';
let mockAgentDescription = '';

vi.mock('next-intl', () => {
  // Stable reference: a fresh translator per render re-triggers effects keyed on `t`.
  const t = (key: string) => {
    const translations: Record<string, string> = {
      title: 'Session Baseline Context Footprint',
      subtitle: 'Pre-flight context token allocation before conversation turns',
      totalBaseline: 'Total Baseline Footprint',
      systemPrompt: 'System Prompt',
      persona: 'Agent Persona',
      workspaceRules: 'Workspace Rules',
      mcpTools: 'MCP Tools Schema',
      skillsTools: 'Skills Tools',
      mcpSwitcherTitle: 'Idle MCP Services Quick Switcher',
      mcpSwitcherDesc: 'Disable unused MCP servers for current session to minimize overhead',
      enabled: 'Enabled',
      disabled: 'Disabled',
      noMcpServers: 'No MCP services configured',
      close: 'Close',
    };
    return translations[key] ?? key;
  };
  return { useTranslations: () => t };
});

vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (state: unknown) => unknown) =>
    selector({
      mcpConfigs: mockMcpConfigs,
      toggleMCPConfig: toggleMCPConfigMock,
      systemInstructions: mockSystemInstructions,
    }),
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: unknown) => unknown) =>
    selector({
      agentConfig: {
        description: mockAgentDescription,
      },
    }),
}));

describe('ContextFootprintInspector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSystemInstructions = 'You are a helpful programming assistant.';
    mockAgentDescription = 'Full-stack software architect.';
    mockMcpConfigs = [
      {
        name: 'sqlite-service',
        description: 'SQLite database inspection service',
        type: 'stdio',
        command: 'uvx mcp-server-sqlite',
        enabled: true,
      },
      {
        name: 'puppeteer-service',
        description: 'Browser automation service',
        type: 'stdio',
        command: 'npx mcp-puppeteer',
        enabled: false,
      },
    ];
  });

  describe('formatTokenNumber utility', () => {
    it('formats numbers under 1000 without suffix', () => {
      expect(formatTokenNumber(0)).toBe('0');
      expect(formatTokenNumber(800)).toBe('800');
      expect(formatTokenNumber(999)).toBe('999');
    });

    it('formats thousands with k suffix and compact decimals', () => {
      expect(formatTokenNumber(1000)).toBe('1k');
      expect(formatTokenNumber(2500)).toBe('2.5k');
      expect(formatTokenNumber(12000)).toBe('12k');
      expect(formatTokenNumber(12400)).toBe('12.4k');
    });
  });

  describe('Component rendering and interactions', () => {
    it('returns null when open is false', () => {
      const { container } = render(<ContextFootprintInspector open={false} onClose={vi.fn()} />);
      expect(container.firstChild).toBeNull();
    });

    it('renders 5-layer breakdown and baseline summary when open is true', () => {
      render(<ContextFootprintInspector open={true} onClose={vi.fn()} />);

      expect(screen.getByTestId('context-footprint-inspector')).toBeDefined();
      expect(screen.getByText('Session Baseline Context Footprint')).toBeDefined();
      expect(screen.getByText('System Prompt')).toBeDefined();
      expect(screen.getByText('Agent Persona')).toBeDefined();
      expect(screen.getByText('Workspace Rules')).toBeDefined();
      expect(screen.getByText('MCP Tools Schema')).toBeDefined();
      expect(screen.getByText('Skills Tools')).toBeDefined();
    });

    it('renders idle MCP switcher items and calls toggleMCPConfig when toggled', () => {
      render(<ContextFootprintInspector open={true} onClose={vi.fn()} />);

      expect(screen.getByText('sqlite-service')).toBeDefined();
      expect(screen.getByText('puppeteer-service')).toBeDefined();

      const toggleButton0 = screen.getByTestId('mcp-toggle-button-0');
      expect(toggleButton0.textContent).toContain('Enabled');

      const toggleButton1 = screen.getByTestId('mcp-toggle-button-1');
      expect(toggleButton1.textContent).toContain('Disabled');

      fireEvent.click(toggleButton0);
      expect(toggleMCPConfigMock).toHaveBeenCalledWith(0);

      fireEvent.click(toggleButton1);
      expect(toggleMCPConfigMock).toHaveBeenCalledWith(1);
    });

    it('calls onClose when close button is clicked', () => {
      const handleClose = vi.fn();
      render(<ContextFootprintInspector open={true} onClose={handleClose} />);

      const closeButton = screen.getByLabelText('Close');
      fireEvent.click(closeButton);
      expect(handleClose).toHaveBeenCalledTimes(1);
    });

    it('renders empty message when no MCP services are configured', () => {
      mockMcpConfigs = [];
      render(<ContextFootprintInspector open={true} onClose={vi.fn()} />);

      expect(screen.getByText('No MCP services configured')).toBeDefined();
    });
  });
});
