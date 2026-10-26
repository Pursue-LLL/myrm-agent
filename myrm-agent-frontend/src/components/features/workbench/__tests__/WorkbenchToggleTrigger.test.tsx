/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkbenchToggleTrigger } from '../WorkbenchToggleTrigger';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('WorkbenchToggleTrigger component', () => {
  beforeEach(() => {
    useWorkbenchStore.setState({
      isOpen: false,
      closeGuard: null,
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

  it('keeps the drawer open when the capsule or the shortcut would close it against the close guard', () => {
    const guard = vi.fn(() => false);
    useWorkbenchStore.setState({ isOpen: true, closeGuard: guard });
    render(<WorkbenchToggleTrigger />);

    fireEvent.click(screen.getByRole('button', { name: /hudActive/i }));
    fireEvent.keyDown(window, { key: 'b', ctrlKey: true, shiftKey: true });

    expect(guard).toHaveBeenCalledTimes(2);
    expect(useWorkbenchStore.getState().isOpen).toBe(true);
  });

  it('menu mode renders nothing but keeps the global shortcut alive', () => {
    const { container } = render(<WorkbenchToggleTrigger showTrigger={false} />);
    expect(container.firstChild).toBeNull();

    fireEvent.keyDown(window, { key: 'b', metaKey: true, shiftKey: true });
    expect(useWorkbenchStore.getState().isOpen).toBe(true);
  });
});
