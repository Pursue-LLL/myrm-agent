import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ComponentProps, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatItem } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';

const services = vi.hoisted(() => ({
  exportSessionZipPack: vi.fn(),
  moveChatToProject: vi.fn(),
  toastError: vi.fn(),
}));
vi.mock('@/services/chatExportPack', () => ({ exportSessionZipPack: services.exportSessionZipPack }));
vi.mock('@/services/projects', () => ({ moveChatToProject: services.moveChatToProject }));
vi.mock('@/lib/utils/toast', () => ({ toast: { error: services.toastError } }));

vi.mock('next/link', () => ({
  default: ({ children, ...props }: ComponentProps<'a'>) => <a {...props}>{children}</a>,
}));
vi.mock('hugeicons-react', () => ({
  AiNetworkIcon: () => <span data-testid="ai-network-icon" />,
}));
vi.mock('@/components/features/settings/sections/integration/channels/ChannelIcon', () => ({
  default: ({ channelId, size }: { channelId: string; size?: number }) => (
    <span data-testid="channel-icon" data-channel={channelId} data-size={size} />
  ),
}));
vi.mock('@/components/primitives/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: ReactNode }) => <div data-testid="dropdown">{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  DropdownMenuContent: ({
    children,
    className,
    ...rest
  }: {
    children: ReactNode;
    className?: string;
    align?: string;
    side?: string;
    sideOffset?: number;
  }) => (
    <div
      data-testid="menu"
      data-align={rest.align}
      data-side={rest.side}
      data-side-offset={rest.sideOffset}
      className={className}
    >
      {children}
    </div>
  ),
  DropdownMenuItem: ({
    children,
    onClick,
    disabled,
    className,
  }: {
    children: ReactNode;
    onClick?: () => void;
    disabled?: boolean;
    className?: string;
  }) => (
    <button type="button" role="menuitem" onClick={onClick} disabled={disabled} className={className}>
      {children}
    </button>
  ),
  DropdownMenuSub: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuSubTrigger: ({
    children,
    disabled,
    className,
  }: {
    children: ReactNode;
    disabled?: boolean;
    className?: string;
  }) => (
    <div role="menuitem" aria-disabled={disabled ? 'true' : undefined} className={className}>
      {children}
    </div>
  ),
  DropdownMenuSubContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

import { ChatHistoryRow, type ChatHistoryRowProps } from '../ChatHistoryRow';

const t = ((key: string) => key) as ChatHistoryRowProps['t'];

const makeChat = (overrides: Partial<ChatItem> = {}): ChatItem => ({
  id: 'chat-1',
  title: 'Quarterly review',
  firstMessage: 'first',
  lastMessage: 'last message text',
  updatedAt: new Date('2026-08-01T12:00:00Z'),
  createdAt: new Date('2026-08-01T10:00:00Z'),
  actionMode: 'agent',
  source: 'web',
  ...overrides,
});

function renderRow(overrides: Partial<ChatHistoryRowProps> = {}) {
  const props: ChatHistoryRowProps = {
    chat: makeChat(),
    isMobile: false,
    isActive: false,
    renameId: null,
    renameValue: '',
    exportingId: null,
    formatTime: (date) => `at ${date.toISOString()}`,
    onItemClick: vi.fn(),
    onRename: vi.fn(),
    onRenameSubmit: vi.fn(),
    onRenameCancel: vi.fn(),
    onRenameValueChange: vi.fn(),
    onDelete: vi.fn(),
    onExport: vi.fn(),
    onPin: vi.fn(),
    onUnpin: vi.fn(),
    t,
    ...overrides,
  };
  const view = render(<ChatHistoryRow {...props} />);
  return { ...view, props, link: screen.getByRole('link') };
}

const item = (name: string) => screen.getByRole('menuitem', { name });

beforeEach(() => {
  vi.clearAllMocks();
  useProjectStore.setState({ projects: [] });
  useChatStore.setState({ chatHistoryItems: [] });
});

describe('ChatHistoryRow link', () => {
  it('opens the chat and reports the click so a drawer can close', () => {
    const { link, props } = renderRow();
    link.addEventListener('click', (event) => event.preventDefault()); // jsdom cannot navigate

    expect(link).toHaveAttribute('href', '/chat-1');
    fireEvent.click(link);

    expect(props.onItemClick).toHaveBeenCalledTimes(1);
  });

  it('turns the row into a selection toggle in batch mode', () => {
    const onToggleSelect = vi.fn();
    const { link, props } = renderRow({ batchMode: true, onToggleSelect });

    expect(link).toHaveAttribute('href', '#');
    const notPrevented = fireEvent.click(link);

    expect(notPrevented).toBe(false);
    expect(onToggleSelect).toHaveBeenCalledWith('chat-1');
    expect(props.onItemClick).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'common.more' })).toBeNull();
  });

  it('shows a checkbox in batch mode that toggles without navigating', () => {
    const onToggleSelect = vi.fn();
    const { container } = renderRow({ batchMode: true, onToggleSelect });
    const checkbox = container.querySelector('button');

    expect(checkbox).not.toBeNull();
    const notPrevented = fireEvent.click(checkbox as HTMLButtonElement);

    expect(notPrevented).toBe(false);
    expect(onToggleSelect).toHaveBeenCalledWith('chat-1');
  });

  it('draws the check mark only for a selected row and tints it', () => {
    const unselected = renderRow({ batchMode: true, isSelected: false });
    expect(unselected.container.querySelector('svg path[d^="M2.5 6"]')).toBeNull();
    expect(unselected.link.className).not.toContain('bg-primary/8');
    unselected.unmount();

    const { container, link } = renderRow({ batchMode: true, isSelected: true });
    expect(container.querySelector('svg path[d^="M2.5 6"]')).not.toBeNull();
    expect(link.className).toContain('bg-primary/8');
  });

  it('marks the active row outside batch mode only', () => {
    const active = renderRow({ isActive: true });
    expect(active.link.className).toContain('brand-selected-surface');
    active.unmount();

    const batch = renderRow({ isActive: true, batchMode: true });
    expect(batch.link.className).not.toContain('brand-selected-surface');
  });

  it('draws a left border in the color of the chat project', () => {
    useProjectStore.setState({ projects: [{ id: 'p1', name: 'Atlas', color: '#336699' } as never] });

    const { link } = renderRow({ chat: makeChat({ projectId: 'p1' }) });

    expect(link.className).toContain('border-l-2');
    expect(link.style.borderLeftColor).toBe('rgb(51, 102, 153)');
  });

  it('draws no border for a chat outside any project', () => {
    const { link } = renderRow();

    expect(link.className).not.toContain('border-l-2');
    expect(link.style.borderLeftColor).toBe('');
  });
});

describe('ChatHistoryRow content', () => {
  it('picks the icon by channel and action mode, smaller on a phone', () => {
    const channel = renderRow({ chat: makeChat({ source: 'telegram' }), isMobile: true });
    expect(screen.getByTestId('channel-icon')).toHaveAttribute('data-channel', 'telegram');
    expect(screen.getByTestId('channel-icon')).toHaveAttribute('data-size', '14');
    channel.unmount();

    const agent = renderRow();
    expect(screen.getByTestId('ai-network-icon')).toBeInTheDocument();
    agent.unmount();

    const fast = renderRow({ chat: makeChat({ actionMode: 'fast' }) });
    expect(screen.queryByTestId('ai-network-icon')).toBeNull();
    expect(screen.queryByTestId('channel-icon')).toBeNull();
    expect(fast.link.querySelector('svg')).toHaveAttribute('width', '16');
  });

  it('shows the title, the last message and the formatted time', () => {
    renderRow();

    expect(screen.getByText('Quarterly review')).toBeInTheDocument();
    expect(screen.getByText('last message text')).toBeInTheDocument();
    expect(screen.getByText('at 2026-08-01T12:00:00.000Z')).toBeInTheDocument();
  });

  it('badges a compacted chat', () => {
    renderRow({ chat: makeChat({ isCompacted: true }) });

    expect(screen.getByText('chat.compact.badge')).toBeInTheDocument();
  });

  it('shows no badge for an uncompacted chat', () => {
    renderRow();

    expect(screen.queryByText('chat.compact.badge')).toBeNull();
  });

  it('shows a pulsing green dot while generating', () => {
    const { container } = renderRow({ isGenerating: true });

    expect(container.querySelector('.animate-ping.bg-emerald-500')).not.toBeNull();
    expect(container.querySelector('.bg-amber-500')).toBeNull();
  });

  it('shows an amber dot while waiting for an approval, even when generating', () => {
    const { container } = renderRow({ isGenerating: true, sessionStatus: 'awaiting_approval' });

    expect(container.querySelector('.bg-amber-500')).not.toBeNull();
    expect(container.querySelector('.bg-emerald-500')).toBeNull();
  });

  it('shows no dot for an idle chat', () => {
    const { container } = renderRow();

    expect(container.querySelector('.bg-amber-500, .bg-emerald-500')).toBeNull();
  });

  it('shows the pin number of a pinned row', () => {
    const { container } = renderRow({ pinIndex: 2 });

    expect(container.querySelector('kbd')).toHaveTextContent('2');
  });

  it('shows no pin number without a pin index', () => {
    const { container } = renderRow();

    expect(container.querySelector('kbd')).toBeNull();
  });

  it('shrinks the title on a phone', () => {
    renderRow({ isMobile: true });

    expect(screen.getByText('Quarterly review').className).toContain('text-xs');
  });
});

describe('ChatHistoryRow rename', () => {
  it('edits the title in place and focuses the field', () => {
    renderRow({ renameId: 'chat-1', renameValue: 'Draft title' });

    const input = screen.getByRole('textbox');
    expect(input).toHaveValue('Draft title');
    expect(input).toHaveFocus();
    expect(screen.queryByText('Quarterly review')).toBeNull();
  });

  it('keeps the title for a row that is not being renamed', () => {
    renderRow({ renameId: 'another-chat' });

    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.getByText('Quarterly review')).toBeInTheDocument();
  });

  it('reports typing, submits on Enter and on blur, cancels on Escape', () => {
    const { props } = renderRow({ renameId: 'chat-1', renameValue: 'x' });
    const input = screen.getByRole('textbox');

    fireEvent.change(input, { target: { value: 'xy' } });
    expect(props.onRenameValueChange).toHaveBeenCalledWith('xy');

    fireEvent.keyDown(input, { key: 'Enter' });
    expect(props.onRenameSubmit).toHaveBeenCalledTimes(1);
    expect(props.onRenameSubmit).toHaveBeenLastCalledWith('chat-1');

    fireEvent.keyDown(input, { key: 'Escape' });
    expect(props.onRenameCancel).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(input, { key: 'a' });
    expect(props.onRenameSubmit).toHaveBeenCalledTimes(1);
    expect(props.onRenameCancel).toHaveBeenCalledTimes(1);

    fireEvent.blur(input);
    expect(props.onRenameSubmit).toHaveBeenCalledTimes(2);
  });

  it('keeps a click inside the field from following the link', () => {
    renderRow({ renameId: 'chat-1', renameValue: 'x' });

    expect(fireEvent.click(screen.getByRole('textbox'))).toBe(false);
  });
});

describe('ChatHistoryRow session drag', () => {
  it('lets the row be dragged into the composer when enabled', () => {
    const onSessionDragStart = vi.fn();
    const { link } = renderRow({ sessionDragEnabled: true, onSessionDragStart });

    expect(link).toHaveAttribute('draggable', 'true');
    expect(link).toHaveAttribute('title', 'chat.dragDrop.sessionDescription');
    fireEvent.dragStart(link);

    expect(onSessionDragStart).toHaveBeenCalledTimes(1);
    expect(onSessionDragStart.mock.calls[0]?.[0]).toMatchObject({ id: 'chat-1' });
  });

  it.each([
    ['disabled', { sessionDragEnabled: false }, false],
    ['selecting in batch mode', { sessionDragEnabled: true, batchMode: true }, false],
    // The hint depends only on the drag being offered, not on whether this row is being renamed.
    ['being renamed', { sessionDragEnabled: true, renameId: 'chat-1' }, true],
  ] as const)('keeps the row still while %s', (_name, overrides, hasHint) => {
    const onSessionDragStart = vi.fn();
    const { link } = renderRow({ ...overrides, onSessionDragStart });

    expect(link).toHaveAttribute('draggable', 'false');
    expect(link.hasAttribute('title')).toBe(hasHint);
    fireEvent.dragStart(link);

    expect(onSessionDragStart).not.toHaveBeenCalled();
  });
});

describe('ChatHistoryRow menu', () => {
  it('names the trigger and sizes the menu for a mouse or a finger', () => {
    const desktop = renderRow();
    expect(screen.getByRole('button', { name: 'common.more' })).toBeInTheDocument();
    expect(screen.getByTestId('menu')).toHaveAttribute('data-align', 'end');
    expect(screen.getByTestId('menu')).toHaveAttribute('data-side', 'bottom');
    expect(screen.getByTestId('menu')).toHaveAttribute('data-side-offset', '4');
    expect(screen.getByTestId('menu').className).toContain('min-w-[140px]');
    expect(item('common.rename').className).not.toContain('min-h-[44px]');
    desktop.unmount();

    renderRow({ isMobile: true });
    expect(screen.getByTestId('menu').className).toContain('min-w-[160px]');
    expect(item('common.rename').className).toContain('min-h-[44px]');
  });

  it('pins an unpinned chat', () => {
    const { props } = renderRow();

    fireEvent.click(item('chat.pin.action'));

    expect(props.onPin).toHaveBeenCalledWith('chat-1');
    expect(screen.queryByRole('menuitem', { name: 'chat.unpin.action' })).toBeNull();
  });

  it('unpins a pinned chat', () => {
    const { props } = renderRow({ chat: makeChat({ isPinned: true }) });

    fireEvent.click(item('chat.unpin.action'));

    expect(props.onUnpin).toHaveBeenCalledWith('chat-1');
    expect(screen.queryByRole('menuitem', { name: 'chat.pin.action' })).toBeNull();
  });

  it('opens the chat in a new window when the desktop shell offers it', () => {
    const onOpenInNewWindow = vi.fn();
    renderRow({ onOpenInNewWindow });

    fireEvent.click(item('chat.openInNewWindow'));

    expect(onOpenInNewWindow).toHaveBeenCalledWith('chat-1');
  });

  it('creates an automation from the chat id and title', () => {
    const onCreateAutomation = vi.fn();
    renderRow({ onCreateAutomation });

    fireEvent.click(item('chat.createAutomation'));

    expect(onCreateAutomation).toHaveBeenCalledWith('chat-1', 'Quarterly review');
  });

  it('hands the chat off with its source', () => {
    const onHandoff = vi.fn();
    renderRow({ onHandoff, chat: makeChat({ source: 'telegram' }) });

    fireEvent.click(item('chat.handoff.menuAction'));

    expect(onHandoff).toHaveBeenCalledWith('chat-1', 'Quarterly review', 'telegram');
  });

  it('forks the chat', () => {
    const onFork = vi.fn();
    renderRow({ onFork });

    fireEvent.click(item('chat.fork.buttonTitle'));

    expect(onFork).toHaveBeenCalledWith('chat-1');
  });

  it('renames with the whole chat', () => {
    const { props } = renderRow();

    fireEvent.click(item('common.rename'));

    expect(props.onRename).toHaveBeenCalledWith(props.chat);
  });

  it('shares the chat', () => {
    const onShare = vi.fn();
    renderRow({ onShare });

    fireEvent.click(item('chat.share.share'));

    expect(onShare).toHaveBeenCalledWith('chat-1');
  });

  it('deletes the chat with a destructive item', () => {
    const { props } = renderRow();

    fireEvent.click(item('common.delete'));

    expect(props.onDelete).toHaveBeenCalledWith('chat-1');
    expect(item('common.delete').className).toContain('text-destructive');
  });

  it.each([
    ['chat.openInNewWindow'],
    ['chat.createAutomation'],
    ['chat.handoff.menuAction'],
    ['chat.fork.buttonTitle'],
    ['chat.share.share'],
    ['chat.ideHandoff.openInIDE'],
    ['chat.revealArtifacts.action'],
    ['chat.captureEvalCase.action'],
  ])('hides %s without its handler', (name) => {
    renderRow();

    expect(screen.queryByRole('menuitem', { name })).toBeNull();
  });

  it.each([
    ['chat.exportChat.exportHtml', 'html'],
    ['chat.exportChat.exportMarkdown', 'markdown'],
    ['chat.exportChat.exportJson', 'json'],
    ['chat.exportChat.copyMarkdown', 'copy'],
    ['chat.exportChat.print', 'print'],
  ] as const)('exports with %s', (name, mode) => {
    const { props } = renderRow();

    fireEvent.click(item(name));

    expect(props.onExport).toHaveBeenCalledWith('chat-1', mode);
  });

  it('exports a ZIP pack', () => {
    services.exportSessionZipPack.mockResolvedValue(undefined);
    renderRow();

    fireEvent.click(item('chat.exportChat.exportZipPack'));

    expect(services.exportSessionZipPack).toHaveBeenCalledWith('chat-1');
  });

  it('reports a failed ZIP export with its own message, or a generic one', async () => {
    renderRow();
    services.exportSessionZipPack.mockRejectedValueOnce(new Error('disk full'));
    fireEvent.click(item('chat.exportChat.exportZipPack'));
    await vi.waitFor(() => expect(services.toastError).toHaveBeenCalledWith('disk full'));

    services.exportSessionZipPack.mockRejectedValueOnce('boom');
    fireEvent.click(item('chat.exportChat.exportZipPack'));
    await vi.waitFor(() => expect(services.toastError).toHaveBeenLastCalledWith('chat.exportChat.exportZipFailed'));
  });

  it('shows progress and blocks a second export while exporting this chat', () => {
    renderRow({ exportingId: 'chat-1', onOpenInIDE: vi.fn() });

    expect(item('chat.exportChat.exporting')).toHaveAttribute('aria-disabled', 'true');
    expect(item('chat.ideHandoff.openInIDE')).toHaveAttribute('aria-disabled', 'true');
  });

  it('keeps export enabled while another chat is exporting', () => {
    renderRow({ exportingId: 'another-chat' });

    expect(item('common.export')).not.toHaveAttribute('aria-disabled');
  });
});

describe('ChatHistoryRow move to project', () => {
  const projects = [
    { id: 'p1', name: 'Atlas', color: '#336699' },
    { id: 'p2', name: 'Borealis', color: '#aa5500' },
  ] as never[];

  it('offers no move without any project', () => {
    renderRow();

    expect(screen.queryByRole('menuitem', { name: 'project.moveTo' })).toBeNull();
  });

  it('lists every project for a chat outside projects', () => {
    useProjectStore.setState({ projects });
    renderRow();

    expect(item('project.moveTo')).toBeInTheDocument();
    expect(item('Atlas')).not.toBeDisabled();
    expect(item('Borealis')).not.toBeDisabled();
    expect(screen.queryByRole('menuitem', { name: 'project.removeFromProject' })).toBeNull();
  });

  it('moves the chat and updates the cached history item', async () => {
    services.moveChatToProject.mockResolvedValue(undefined);
    useProjectStore.setState({ projects });
    useChatStore.setState({ chatHistoryItems: [makeChat(), makeChat({ id: 'chat-2' })] });
    renderRow();

    fireEvent.click(item('Borealis'));

    await vi.waitFor(() => expect(services.moveChatToProject).toHaveBeenCalledWith('chat-1', 'p2'));
    await vi.waitFor(() =>
      expect(useChatStore.getState().chatHistoryItems.map((chat) => [chat.id, chat.projectId])).toEqual([
        ['chat-1', 'p2'],
        ['chat-2', undefined],
      ]),
    );
  });

  it('marks the current project and offers to leave it', async () => {
    services.moveChatToProject.mockResolvedValue(undefined);
    useProjectStore.setState({ projects });
    useChatStore.setState({ chatHistoryItems: [makeChat({ projectId: 'p1' })] });
    renderRow({ chat: makeChat({ projectId: 'p1' }) });

    const current = item('Atlasproject.current');
    expect(current).toBeDisabled();
    expect(within(current).getByText('project.current')).toBeInTheDocument();

    fireEvent.click(item('project.removeFromProject'));

    await vi.waitFor(() => expect(services.moveChatToProject).toHaveBeenCalledWith('chat-1', null));
    await vi.waitFor(() => expect(useChatStore.getState().chatHistoryItems[0]?.projectId).toBeNull());
  });
});
