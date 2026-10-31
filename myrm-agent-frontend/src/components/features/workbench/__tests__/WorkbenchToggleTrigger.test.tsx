/** @vitest-environment jsdom */
import { fireEvent, render } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { WorkbenchToggleTrigger } from '../WorkbenchToggleTrigger';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';

describe('WorkbenchToggleTrigger component', () => {
  beforeEach(() => {
    useWorkbenchStore.setState({ isOpen: false });
  });

  it('renders no floating entrance: the Tools menu is the only visible way in', () => {
    const { container } = render(<WorkbenchToggleTrigger />);
    expect(container.firstChild).toBeNull();
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

  it('closes an open workbench from the shortcut', () => {
    useWorkbenchStore.setState({ isOpen: true });
    render(<WorkbenchToggleTrigger />);

    fireEvent.keyDown(window, { key: 'b', ctrlKey: true, shiftKey: true });
    expect(useWorkbenchStore.getState().isOpen).toBe(false);
  });

  it('stops listening once unmounted', () => {
    const { unmount } = render(<WorkbenchToggleTrigger />);
    unmount();

    fireEvent.keyDown(window, { key: 'b', metaKey: true, shiftKey: true });
    window.dispatchEvent(new CustomEvent('myrm:open-workbench'));
    expect(useWorkbenchStore.getState().isOpen).toBe(false);
  });
});
