/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkbenchToggleTrigger } from '../WorkbenchToggleTrigger';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

describe('WorkbenchToggleTrigger component', () => {
  beforeEach(() => {
    useWorkbenchStore.setState({
      isOpen: false,
    });
  });

  it('renders closed HUD capsule initially with trigger hint', () => {
    render(<WorkbenchToggleTrigger />);

    const triggerBtn = screen.getByRole('button', { name: /hudTrigger/i });
    expect(triggerBtn).toBeDefined();
    expect(screen.getByText('shortcutHint')).toBeDefined();
  });

  it('toggles open state on button click', () => {
    render(<WorkbenchToggleTrigger />);

    const triggerBtn = screen.getByRole('button', { name: /hudTrigger/i });
    fireEvent.click(triggerBtn);

    expect(useWorkbenchStore.getState().isOpen).toBe(true);

    fireEvent.click(triggerBtn);
    expect(useWorkbenchStore.getState().isOpen).toBe(false);
  });

  it('toggles open state when Cmd+Shift+B is pressed', () => {
    render(<WorkbenchToggleTrigger />);

    expect(useWorkbenchStore.getState().isOpen).toBe(false);

    fireEvent.keyDown(window, {
      key: 'b',
      metaKey: true,
      shiftKey: true,
    });

    expect(useWorkbenchStore.getState().isOpen).toBe(true);

    fireEvent.keyDown(window, {
      key: 'b',
      ctrlKey: true,
      shiftKey: true,
    });

    expect(useWorkbenchStore.getState().isOpen).toBe(false);
  });

  it('opens workbench on custom event myrm:open-workbench', () => {
    render(<WorkbenchToggleTrigger />);

    expect(useWorkbenchStore.getState().isOpen).toBe(false);

    window.dispatchEvent(new CustomEvent('myrm:open-workbench'));
    expect(useWorkbenchStore.getState().isOpen).toBe(true);
  });
});
