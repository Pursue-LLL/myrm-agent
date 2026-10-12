/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DesignerEyeOverlay } from '../DesignerEyeOverlay';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconEye: () => <span data-testid="icon-eye" />,
  IconX: () => <span data-testid="icon-x" />,
  IconSparkles: () => <span data-testid="icon-sparkles" />,
  IconCheck: () => <span data-testid="icon-check" />,
  IconRefresh: () => <span data-testid="icon-refresh" />,
}));

describe('DesignerEyeOverlay component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders floating HUD switcher trigger in idle state', () => {
    render(<DesignerEyeOverlay />);

    const triggerBtn = screen.getByRole('button', { name: /inspectorTrigger/i });
    expect(triggerBtn).toBeDefined();
    expect(screen.getByText('shortcutHint')).toBeDefined();
  });

  it('toggles active inspector mode when clicking trigger button', () => {
    render(<DesignerEyeOverlay />);

    const triggerBtn = screen.getByRole('button', { name: /inspectorTrigger/i });
    fireEvent.click(triggerBtn);

    expect(screen.getByText('inspectorActive')).toBeDefined();
    expect(screen.getByRole('button', { name: 'closeInspectorAriaLabel' })).toBeDefined();

    // Click close button to deactivate
    const closeBtn = screen.getByRole('button', { name: 'closeInspectorAriaLabel' });
    fireEvent.click(closeBtn);
    expect(screen.getByText('inspectorTrigger')).toBeDefined();
  });

  it('toggles active inspector mode on Cmd+Shift+E shortcut', () => {
    render(<DesignerEyeOverlay />);

    // Press Cmd+Shift+E
    fireEvent.keyDown(window, {
      key: 'e',
      metaKey: true,
      shiftKey: true,
    });

    expect(screen.getByText('inspectorActive')).toBeDefined();

    // Press Escape to exit
    fireEvent.keyDown(window, {
      key: 'Escape',
    });

    expect(screen.getByText('inspectorTrigger')).toBeDefined();
  });

  it('activates and selects element on click, opening feedback modal', () => {
    // Render dummy target node in document body
    const targetDiv = document.createElement('div');
    targetDiv.className = 'test-card-class';
    targetDiv.id = 'unique-element-id';
    targetDiv.setAttribute('data-component', 'features/TestComponent');
    document.body.appendChild(targetDiv);

    // Mock elementFromPoint to return targetDiv
    document.elementFromPoint = vi.fn().mockReturnValue(targetDiv);

    render(<DesignerEyeOverlay />);

    // Activate inspector
    const triggerBtn = screen.getByRole('button', { name: /inspectorTrigger/i });
    fireEvent.click(triggerBtn);

    // Trigger click on element
    fireEvent.click(targetDiv);

    // Modal should open
    expect(screen.getByText('modalTitle')).toBeDefined();
    expect(screen.getAllByText('features/TestComponent').length).toBeGreaterThanOrEqual(1);

    // Cleanup
    document.body.removeChild(targetDiv);
  });
});
