/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkspaceLayoutBar } from '../WorkspaceLayoutBar';
import * as layoutHook from '@/hooks/ui/useWorkspaceLayoutMode';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconCpu: () => <span data-testid="icon-cpu" />,
  IconSparkles: () => <span data-testid="icon-sparkles" />,
  IconTerminal: () => <span data-testid="icon-terminal" />,
  IconUsers: () => <span data-testid="icon-users" />,
  IconCheck: () => <span data-testid="icon-check" />,
  IconX: () => <span data-testid="icon-x" />,
}));

describe('WorkspaceLayoutBar component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(layoutHook, 'useWorkspaceLayoutMode').mockReturnValue({
      layoutMode: 'copilot',
      setLayoutMode: vi.fn(),
      resetLayout: vi.fn(),
      isCopilot: true,
      isMultiAgent: false,
      isRemoteCompute: false,
      isEasyMinimal: false,
    });
  });

  it('renders layout bar with active layout label and shortcut hint', () => {
    render(<WorkspaceLayoutBar />);

    expect(screen.getByText('copilotShortLabel')).toBeDefined();
    expect(screen.getByText('shortcutHint')).toBeDefined();
  });

  it('opens layout choice modal when clicking the bar button', () => {
    render(<WorkspaceLayoutBar />);

    const barBtn = screen.getByRole('button', { name: /copilotShortLabel/i });
    fireEvent.click(barBtn);

    expect(screen.getByText('modalTitle')).toBeDefined();
  });

  it('toggles layout modal on Cmd+Shift+L shortcut and closes on Escape', () => {
    render(<WorkspaceLayoutBar />);

    // Press Cmd+Shift+L to open
    fireEvent.keyDown(window, {
      key: 'l',
      metaKey: true,
      shiftKey: true,
    });

    expect(screen.getByText('modalTitle')).toBeDefined();

    // Press Escape to close
    fireEvent.keyDown(window, {
      key: 'Escape',
    });

    expect(screen.queryByText('modalTitle')).toBeNull();
  });
});
