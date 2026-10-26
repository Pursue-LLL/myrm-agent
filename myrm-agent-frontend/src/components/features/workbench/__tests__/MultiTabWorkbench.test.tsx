/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MultiTabWorkbench } from '../MultiTabWorkbench';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';
import useChatStore from '@/store/useChatStore';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

// Shows the chat it was mounted for, so a remount on chat switch is observable.
vi.mock('../tabs/WorkbenchFiles', () => ({
  WorkbenchFiles: () => {
    const [mountedFor] = useState(() => useChatStore.getState().chatId);
    return <div data-testid="tab-files-content">Files of {mountedFor}</div>;
  },
}));

vi.mock('../tabs/WorkbenchTerminal', () => ({
  WorkbenchTerminal: ({ chatId }: { chatId: string }) => (
    <div data-testid="tab-terminal-content">Terminal of {chatId}</div>
  ),
}));

describe('MultiTabWorkbench component', () => {
  beforeEach(() => {
    useWorkbenchStore.setState({
      isOpen: true,
      placement: 'right',
      width: 480,
      height: 320,
      activeTab: 'files',
      terminalLogs: [],
    });
    useChatStore.setState({ chatId: 'chat-1' });
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
