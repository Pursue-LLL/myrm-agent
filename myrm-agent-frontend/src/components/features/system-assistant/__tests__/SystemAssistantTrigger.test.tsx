/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SystemAssistantTrigger } from '../SystemAssistantTrigger';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconBrain: () => <span data-testid="icon-brain" />,
  IconSparkles: () => <span data-testid="icon-sparkles" />,
  IconCheck: () => <span data-testid="icon-check" />,
  IconClose: () => <span data-testid="icon-close" />,
  IconRefresh: () => <span data-testid="icon-refresh" />,
  IconTerminal: () => <span data-testid="icon-terminal" />,
  IconX: () => <span data-testid="icon-x" />,
}));

vi.mock('@/services/systemAssistant', () => ({
  executeSystemAssistantCommand: vi.fn(),
  getSystemAssistantStatus: vi.fn().mockResolvedValue({
    active_agents_count: 2,
    running_tasks_count: 1,
    total_projects_count: 3,
    system_health: 'optimal',
    voice_enabled: true,
    last_heartbeat: '2026-10-12T07:00:00Z',
  }),
}));

describe('SystemAssistantTrigger component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders floating launcher button with assistant name and shortcut hint', () => {
    render(<SystemAssistantTrigger />);

    const launcherBtn = screen.getByRole('button', { name: /assistantName/i });
    expect(launcherBtn).toBeDefined();
    expect(screen.getByText('shortcutHint')).toBeDefined();
  });

  it('opens modal when clicking launcher button', async () => {
    render(<SystemAssistantTrigger />);

    const launcherBtn = screen.getByRole('button', { name: /assistantName/i });
    fireEvent.click(launcherBtn);

    await waitFor(() => {
      expect(screen.getByText('hubTitle')).toBeDefined();
    });
  });

  it('toggles modal on Cmd+J keyboard shortcut and closes on Escape', async () => {
    render(<SystemAssistantTrigger />);

    // Press Cmd+J to open
    fireEvent.keyDown(window, {
      key: 'j',
      metaKey: true,
    });

    await waitFor(() => {
      expect(screen.getByText('hubTitle')).toBeDefined();
    });

    // Press Escape to close
    fireEvent.keyDown(window, {
      key: 'Escape',
    });

    expect(screen.queryByText('hubTitle')).toBeNull();
  });

  it('menu mode hides the launcher and opens from the utility event', async () => {
    render(<SystemAssistantTrigger showTrigger={false} />);
    expect(screen.queryByRole('button', { name: /assistantName/i })).toBeNull();

    act(() => {
      window.dispatchEvent(new Event('myrm:open-system-assistant'));
    });

    await waitFor(() => {
      expect(screen.getByText('hubTitle')).toBeDefined();
    });
  });
});
