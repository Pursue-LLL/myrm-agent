/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MultiTabWorkbench } from '../MultiTabWorkbench';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';
import useChatStore from '@/store/useChatStore';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

// Shows the chat it was mounted for, so a remount on chat switch is observable; the clip stands for a preview.
vi.mock('../tabs/WorkbenchFiles', () => ({
  WorkbenchFiles: () => {
    const [mountedFor] = useState(() => useChatStore.getState().chatId);
    return (
      <div data-testid="tab-files-content">
        Files of {mountedFor}
        <video data-testid="preview-clip">
          <track kind="captions" />
        </video>
      </div>
    );
  },
}));

vi.mock('../tabs/WorkbenchTerminal', () => ({
  WorkbenchTerminal: ({ chatId }: { chatId: string }) => (
    <div data-testid="tab-terminal-content">Terminal of {chatId}</div>
  ),
}));

// jsdom does not implement media playback; the spy stands in for the browser and records who was stopped.
const stubPause = () => vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});

describe('MultiTabWorkbench component', () => {
  let pause: ReturnType<typeof stubPause>;

  beforeEach(() => {
    pause = stubPause();
    useWorkbenchStore.setState({
      isOpen: true,
      placement: 'right',
      width: 480,
      height: 320,
      activeTab: 'files',
      terminalLogs: [],
      closeGuard: null,
    });
    useChatStore.setState({ chatId: 'chat-1' });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders null when isOpen is false', () => {
    useWorkbenchStore.setState({ isOpen: false });
    const { container } = render(<MultiTabWorkbench />);
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer shell, files and terminal tabs, and the active chat files content', () => {
    render(<MultiTabWorkbench />);

    expect(screen.getByRole('complementary', { name: 'workbenchAriaLabel' })).toBeDefined();
    expect(screen.getAllByRole('tab')).toHaveLength(2);
    expect(screen.getByRole('tab', { name: /tabFiles/i })).toBeDefined();
    expect(screen.getByRole('tab', { name: /tabTerminal/i })).toBeDefined();

    expect(screen.getByTestId('tab-files-content').textContent).toBe('Files of chat-1');
  });

  it('asks for a conversation instead of browsing anything when there is no chat', () => {
    useChatStore.setState({ chatId: undefined });

    render(<MultiTabWorkbench />);

    expect(screen.getByText('noChat')).toBeDefined();
    expect(screen.queryByTestId('tab-files-content')).toBeNull();
    expect(screen.queryByTestId('tab-terminal-content')).toBeNull();
  });

  it('drops the previous chat terminal history and remounts the tab when the chat changes', () => {
    render(<MultiTabWorkbench />);
    useWorkbenchStore.setState({
      terminalLogs: [{ id: 'l1', command: 'ls', output: 'x', exitCode: 0, timestamp: '2023-11-14T22:13:20Z' }],
    });

    act(() => {
      useChatStore.setState({ chatId: 'chat-2' });
    });

    expect(useWorkbenchStore.getState().terminalLogs).toHaveLength(0);
    expect(screen.getByTestId('tab-files-content').textContent).toBe('Files of chat-2');
  });

  it('switches active tab when tab buttons are clicked', () => {
    render(<MultiTabWorkbench />);

    const termTabBtn = screen.getByRole('tab', { name: /tabTerminal/i });
    fireEvent.click(termTabBtn);
    expect(useWorkbenchStore.getState().activeTab).toBe('terminal');
    expect(screen.getByTestId('tab-terminal-content').textContent).toBe('Terminal of chat-1');

    fireEvent.click(screen.getByRole('tab', { name: /tabFiles/i }));
    expect(useWorkbenchStore.getState().activeTab).toBe('files');
    expect(screen.getByTestId('tab-files-content')).toBeDefined();
  });

  it('keeps the Files page mounted, only hidden, while the Terminal tab is up', () => {
    render(<MultiTabWorkbench />);
    const filesContent = screen.getByTestId('tab-files-content');
    const filesPanel = filesContent.closest('[role="tabpanel"]');

    fireEvent.click(screen.getByRole('tab', { name: /tabTerminal/i }));

    expect(screen.getByTestId('tab-files-content')).toBe(filesContent);
    expect(filesPanel?.hasAttribute('hidden')).toBe(true);
    expect(screen.getByRole('tabpanel')).toBe(screen.getByTestId('tab-terminal-content').closest('[role="tabpanel"]'));

    fireEvent.click(screen.getByRole('tab', { name: /tabFiles/i }));

    expect(screen.getByTestId('tab-files-content')).toBe(filesContent);
    expect(screen.getByRole('tabpanel')).toBe(filesPanel);
    expect(screen.queryByTestId('tab-terminal-content')).toBeNull();
  });

  it('starts a new Files page, hidden or not, when the chat changes', () => {
    render(<MultiTabWorkbench />);
    fireEvent.click(screen.getByRole('tab', { name: /tabTerminal/i }));
    const before = screen.getByTestId('tab-files-content');

    act(() => {
      useChatStore.setState({ chatId: 'chat-2' });
    });

    expect(screen.getByTestId('tab-files-content')).not.toBe(before);
    expect(screen.getByTestId('tab-files-content').textContent).toContain('Files of chat-2');
  });

  it('stops what the Files page is playing when the Terminal tab comes up, and only then', () => {
    render(<MultiTabWorkbench />);
    expect(pause).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('tab', { name: /tabTerminal/i }));

    expect(pause).toHaveBeenCalledTimes(1);
    expect(pause.mock.contexts[0]).toBe(screen.getByTestId('preview-clip'));

    fireEvent.click(screen.getByRole('tab', { name: /tabFiles/i }));

    expect(pause).toHaveBeenCalledTimes(1);
  });

  it('connects each tab with its panel for assistive technology', () => {
    render(<MultiTabWorkbench />);
    const tablist = screen.getByRole('tablist');
    const filesTab = screen.getByRole('tab', { name: /tabFiles/i });
    const terminalTab = screen.getByRole('tab', { name: /tabTerminal/i });
    const filesPanel = screen.getByRole('tabpanel');

    expect(tablist.contains(filesTab) && tablist.contains(terminalTab)).toBe(true);
    expect(filesTab.getAttribute('aria-controls')).toBe(filesPanel.id);
    expect(filesPanel.getAttribute('aria-labelledby')).toBe(filesTab.id);

    fireEvent.click(terminalTab);
    const terminalPanel = screen.getByRole('tabpanel');

    expect(terminalPanel).not.toBe(filesPanel);
    expect(terminalTab.getAttribute('aria-controls')).toBe(terminalPanel.id);
    expect(terminalPanel.getAttribute('aria-labelledby')).toBe(terminalTab.id);
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

  it.each(['input', 'textarea'])('keeps the workbench open when Escape is pressed in a %s', (tagName) => {
    render(<MultiTabWorkbench />);
    const field = document.body.appendChild(document.createElement(tagName));

    fireEvent.keyDown(field, { key: 'Escape' });

    expect(useWorkbenchStore.getState().isOpen).toBe(true);
    field.remove();
  });

  it('keeps the workbench open when something else already used the Escape key', () => {
    const consume = (event: KeyboardEvent) => event.preventDefault();
    window.addEventListener('keydown', consume);
    render(<MultiTabWorkbench />);

    fireEvent.keyDown(document.body, { key: 'Escape', cancelable: true });

    expect(useWorkbenchStore.getState().isOpen).toBe(true);
    window.removeEventListener('keydown', consume);
  });

  it('closes workbench on clicking close button', () => {
    render(<MultiTabWorkbench />);

    const closeBtn = screen.getByRole('button', { name: 'closeAction' });
    fireEvent.click(closeBtn);
    expect(useWorkbenchStore.getState().isOpen).toBe(false);
  });

  describe('while a tab holds unsaved work', () => {
    it('keeps the drawer open when the close button or Escape is refused by the close guard', () => {
      const guard = vi.fn(() => false);
      useWorkbenchStore.setState({ closeGuard: guard });
      render(<MultiTabWorkbench />);

      fireEvent.click(screen.getByRole('button', { name: 'closeAction' }));
      fireEvent.keyDown(window, { key: 'Escape' });

      expect(guard).toHaveBeenCalledTimes(2);
      expect(useWorkbenchStore.getState().isOpen).toBe(true);
    });

    it('closes the drawer when the guard agrees', () => {
      useWorkbenchStore.setState({ closeGuard: () => true });
      render(<MultiTabWorkbench />);

      fireEvent.click(screen.getByRole('button', { name: 'closeAction' }));

      expect(useWorkbenchStore.getState().isOpen).toBe(false);
    });
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
