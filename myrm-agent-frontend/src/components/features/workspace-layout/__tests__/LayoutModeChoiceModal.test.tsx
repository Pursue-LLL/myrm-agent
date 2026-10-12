/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LayoutModeChoiceModal } from '../LayoutModeChoiceModal';
import * as layoutHook from '@/hooks/ui/useWorkspaceLayoutMode';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconCheck: () => <span data-testid="icon-check" />,
  IconCpu: () => <span data-testid="icon-cpu" />,
  IconSparkles: () => <span data-testid="icon-sparkles" />,
  IconTerminal: () => <span data-testid="icon-terminal" />,
  IconUsers: () => <span data-testid="icon-users" />,
  IconX: () => <span data-testid="icon-x" />,
}));

describe('LayoutModeChoiceModal component', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
  };

  const mockSetLayoutMode = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(layoutHook, 'useWorkspaceLayoutMode').mockReturnValue({
      layoutMode: 'easy_minimal',
      setLayoutMode: mockSetLayoutMode,
      resetLayout: vi.fn(),
      isCopilot: false,
      isMultiAgent: false,
      isRemoteCompute: false,
      isEasyMinimal: true,
    });
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(
      <LayoutModeChoiceModal {...defaultProps} isOpen={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders modal with 4 layout mode cards', () => {
    render(<LayoutModeChoiceModal {...defaultProps} />);

    expect(screen.getByText('modalTitle')).toBeDefined();
    expect(screen.getByText('copilotTitle')).toBeDefined();
    expect(screen.getByText('multiAgentTitle')).toBeDefined();
    expect(screen.getByText('remoteComputeTitle')).toBeDefined();
    expect(screen.getByText('easyMinimalTitle')).toBeDefined();
    expect(screen.getByTestId('icon-check')).toBeDefined();
  });

  it('switches layout mode when clicking a layout option card', () => {
    render(<LayoutModeChoiceModal {...defaultProps} />);

    const copilotCard = screen.getByText('copilotTitle').closest('button');
    expect(copilotCard).not.toBeNull();
    if (copilotCard) {
      fireEvent.click(copilotCard);
    }

    expect(mockSetLayoutMode).toHaveBeenCalledWith('copilot');
  });

  it('triggers onClose when close or done buttons are clicked', () => {
    render(<LayoutModeChoiceModal {...defaultProps} />);

    const closeBtn = screen.getByRole('button', { name: 'closeAriaLabel' });
    fireEvent.click(closeBtn);
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);

    const doneBtn = screen.getByRole('button', { name: 'doneAction' });
    fireEvent.click(doneBtn);
    expect(defaultProps.onClose).toHaveBeenCalledTimes(2);
  });
});
