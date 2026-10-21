/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DesignerEyeFeedbackModal } from '../DesignerEyeFeedbackModal';
import * as selfEvolutionService from '@/services/selfEvolution';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconCheck: () => <span data-testid="icon-check" />,
  IconRefresh: () => <span data-testid="icon-refresh" />,
  IconSparkles: () => <span data-testid="icon-sparkles" />,
  IconX: () => <span data-testid="icon-x" />,
}));

vi.mock('@/services/selfEvolution', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/selfEvolution')>();
  return {
    ...actual,
    createSelfEvolutionTask: vi.fn(),
    recoverSelfEvolution: vi.fn(),
  };
});

describe('DesignerEyeFeedbackModal component', () => {
  const mockTarget: selfEvolutionService.InspectedElementContext = {
    domSelector: '#mobile-hub > div.card',
    tagName: 'div',
    classes: ['card', 'p-4', 'bg-card'],
    componentHint: 'features/mobile/MobileSessionHub',
    computedStyleSummary: {
      padding: '16px',
      backgroundColor: 'rgb(255, 255, 255)',
    },
  };

  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    target: mockTarget,
    onTaskCreated: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not render when isOpen is false or target is null', () => {
    const { container: c1 } = render(
      <DesignerEyeFeedbackModal {...defaultProps} isOpen={false} />,
    );
    expect(c1.firstChild).toBeNull();

    const { container: c2 } = render(
      <DesignerEyeFeedbackModal {...defaultProps} target={null} />,
    );
    expect(c2.firstChild).toBeNull();
  });

  it('renders modal with target context information', () => {
    render(<DesignerEyeFeedbackModal {...defaultProps} />);

    expect(screen.getByText('modalTitle')).toBeDefined();
    expect(screen.getByText('<div.card>'.replace('.card', ''))).toBeDefined();
    expect(screen.getByText('features/mobile/MobileSessionHub')).toBeDefined();
    expect(screen.getByText('#mobile-hub > div.card')).toBeDefined();
  });

  it('toggles quick preset tags on click', () => {
    render(<DesignerEyeFeedbackModal {...defaultProps} />);

    const darkModeTag = screen.getByRole('button', { name: '#dark_mode' });
    expect(darkModeTag).toBeDefined();

    // Toggle on
    fireEvent.click(darkModeTag);
    // Click again to toggle off
    fireEvent.click(darkModeTag);
  });

  it('submits evolution task with prompt and triggers onTaskCreated', async () => {
    const mockTask: selfEvolutionService.SelfEvolutionTaskResponse = {
      task_id: 'evo-test1234',
      status: 'verified',
      dom_selector: mockTarget.domSelector,
      tag_name: mockTarget.tagName,
      user_prompt: 'Make card padding p-6',
      target_component_file: 'src/components/features/mobile/MobileSessionHub.tsx',
      recoverable_checkpoint_id: 'chk-test1234',
      created_at: '2026-10-12T06:00:00Z',
    };

    vi.mocked(selfEvolutionService.createSelfEvolutionTask).mockResolvedValueOnce(mockTask);

    render(<DesignerEyeFeedbackModal {...defaultProps} />);

    const textarea = screen.getByPlaceholderText('promptPlaceholder');
    fireEvent.change(textarea, { target: { value: 'Make card padding p-6' } });

    const submitBtn = screen.getByRole('button', { name: 'submitEvolutionAction' });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(selfEvolutionService.createSelfEvolutionTask).toHaveBeenCalledWith(
        expect.objectContaining({
          dom_selector: mockTarget.domSelector,
          user_prompt: 'Make card padding p-6',
        }),
      );
    });

    await waitFor(() => {
      expect(defaultProps.onTaskCreated).toHaveBeenCalledWith(mockTask);
      expect(screen.getByText(/evo-test1234/)).toBeDefined();
    });
  });

  it('triggers emergency rollback when clicking rollback button', async () => {
    vi.mocked(selfEvolutionService.recoverSelfEvolution).mockResolvedValueOnce({
      success: true,
      message: 'Restored safely to checkpoint chk-safe',
      restored_checkpoint_id: 'chk-safe',
    });

    render(<DesignerEyeFeedbackModal {...defaultProps} />);

    const rollbackBtn = screen.getByRole('button', { name: 'rollbackAction' });
    fireEvent.click(rollbackBtn);

    await waitFor(() => {
      expect(selfEvolutionService.recoverSelfEvolution).toHaveBeenCalled();
      expect(screen.getByText('Restored safely to checkpoint chk-safe')).toBeDefined();
    });
  });

  it('triggers onClose when close or cancel buttons are clicked', () => {
    render(<DesignerEyeFeedbackModal {...defaultProps} />);

    const closeBtn = screen.getByRole('button', { name: 'closeAriaLabel' });
    fireEvent.click(closeBtn);
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);

    const cancelBtn = screen.getByRole('button', { name: 'cancelAction' });
    fireEvent.click(cancelBtn);
    expect(defaultProps.onClose).toHaveBeenCalledTimes(2);
  });
});
