/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MultiTabWorkbench } from '../MultiTabWorkbench';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('../tabs/WorkbenchFileExplorer', () => ({
  WorkbenchFileExplorer: () => <div data-testid="tab-files-content">Files Content</div>,
}));

vi.mock('../tabs/WorkbenchDiffViewer', () => ({
  WorkbenchDiffViewer: () => <div data-testid="tab-diff-content">Diff Content</div>,
}));

vi.mock('../tabs/WorkbenchTerminal', () => ({
  WorkbenchTerminal: () => <div data-testid="tab-terminal-content">Terminal Content</div>,
}));

vi.mock('../tabs/WorkbenchPluginCenter', () => ({
  WorkbenchPluginCenter: () => <div data-testid="tab-plugins-content">Plugins Content</div>,
}));

describe('MultiTabWorkbench component', () => {
  beforeEach(() => {
    useWorkbenchStore.setState({
      isOpen: true,
      placement: 'right',
      width: 480,
      height: 320,
      activeTab: 'files',
    });
  });

  it('renders null when isOpen is false', () => {
    useWorkbenchStore.setState({ isOpen: false });
    const { container } = render(<MultiTabWorkbench />);
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer shell, 4 tabs, and active files content', () => {
    render(<MultiTabWorkbench />);

    expect(screen.getByRole('complementary', { name: 'workbenchAriaLabel' })).toBeDefined();
    expect(screen.getByRole('tab', { name: /tabFiles/i })).toBeDefined();
    expect(screen.getByRole('tab', { name: /tabDiff/i })).toBeDefined();
    expect(screen.getByRole('tab', { name: /tabTerminal/i })).toBeDefined();
    expect(screen.getByRole('tab', { name: /tabPlugins/i })).toBeDefined();

    expect(screen.getByTestId('tab-files-content')).toBeDefined();
  });

  it('switches active tab when tab buttons are clicked', () => {
    render(<MultiTabWorkbench />);

    // Click Diff tab
    const diffTabBtn = screen.getByRole('tab', { name: /tabDiff/i });
    fireEvent.click(diffTabBtn);
    expect(useWorkbenchStore.getState().activeTab).toBe('diff');
    expect(screen.getByTestId('tab-diff-content')).toBeDefined();

    // Click Terminal tab
    const termTabBtn = screen.getByRole('tab', { name: /tabTerminal/i });
    fireEvent.click(termTabBtn);
    expect(useWorkbenchStore.getState().activeTab).toBe('terminal');
    expect(screen.getByTestId('tab-terminal-content')).toBeDefined();

    // Click Plugins tab
    const pluginsTabBtn = screen.getByRole('tab', { name: /tabPlugins/i });
    fireEvent.click(pluginsTabBtn);
    expect(useWorkbenchStore.getState().activeTab).toBe('plugins');
    expect(screen.getByTestId('tab-plugins-content')).toBeDefined();
  });

  it('switches placement between right and bottom', () => {
    render(<MultiTabWorkbench />);

    const dockBtn = screen.getByRole('button', { name: 'dockBottom' });
    fireEvent.click(dockBtn);
    expect(useWorkbenchStore.getState().placement).toBe('bottom');

    const dockRightBtn = screen.getByRole('button', { name: 'dockRight' });
    fireEvent.click(dockRightBtn);
    expect(useWorkbenchStore.getState().placement).toBe('right');
  });

  it('closes workbench on pressing Escape key', () => {
    render(<MultiTabWorkbench />);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(useWorkbenchStore.getState().isOpen).toBe(false);
  });

  it('closes workbench on clicking close button', () => {
    render(<MultiTabWorkbench />);

    const closeBtn = screen.getByRole('button', { name: 'closeAction' });
    fireEvent.click(closeBtn);
    expect(useWorkbenchStore.getState().isOpen).toBe(false);
  });

  it('handles mouse resize drag interaction', () => {
    render(<MultiTabWorkbench />);

    const handle = screen.getByRole('button', { name: 'resizeHandleAria' });
    fireEvent.mouseDown(handle, { clientX: 500, clientY: 200 });

    fireEvent.mouseMove(window, { clientX: 450, clientY: 200 });
    fireEvent.mouseUp(window);

    // Width should increase by delta 50 (480 + 50 = 530)
    expect(useWorkbenchStore.getState().width).toBe(530);
  });
});
