/**
 * Unit tests for ChatHistoryRow external IDE handoff submenu.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import type { ChatItem } from '@/services/chat';

vi.mock('next/link', () => ({
  default: ({ children, href, className, onClick }: any) => (
    <a href={href} className={className} onClick={onClick}>
      {children}
    </a>
  ),
}));

vi.mock('hugeicons-react', () => ({
  AiNetworkIcon: () => <span data-testid="ai-network-icon" />,
}));

vi.mock('@/components/features/settings/sections/integration/channels/ChannelIcon', () => ({
  default: () => <span data-testid="channel-icon" />,
}));

vi.mock('@/components/primitives/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({
    children,
    onClick,
    disabled,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    disabled?: boolean;
  }) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  DropdownMenuSub: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSubTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSubContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { ChatHistoryRow } from '../ChatHistoryRow';

const mockT = ((key: string) => {
  const dict: Record<string, string> = {
    'chat.ideHandoff.openInIDE': 'Open in IDE',
    'chat.ideHandoff.cursor': 'Cursor',
    'chat.ideHandoff.vscode': 'VS Code',
    'common.rename': 'Rename',
    'common.delete': 'Delete',
    'common.export': 'Export',
  };
  return dict[key] || key;
}) as any;

describe('ChatHistoryRow IDE handoff', () => {
  const dummyChat = {
    id: 'chat-test-456',
    title: 'Test Handoff Session',
    createdAt: new Date(),
    updatedAt: new Date(),
  } as ChatItem;

  function renderRow(onOpenInIDE?: (id: string, target: 'cursor' | 'vscode') => void) {
    render(
      <ChatHistoryRow
        chat={dummyChat}
        isMobile={false}
        isActive={false}
        renameId={null}
        renameValue=""
        exportingId={null}
        formatTime={() => '12:00'}
        onRename={vi.fn()}
        onRenameSubmit={vi.fn()}
        onRenameCancel={vi.fn()}
        onRenameValueChange={vi.fn()}
        onDelete={vi.fn()}
        onExport={vi.fn()}
        onOpenInIDE={onOpenInIDE}
        onPin={vi.fn()}
        onUnpin={vi.fn()}
        t={mockT}
      />,
    );
  }

  it('renders the IDE submenu with both targets', () => {
    renderRow(vi.fn());
    expect(screen.getByText('Open in IDE')).toBeInTheDocument();
    expect(screen.getByText('Cursor')).toBeInTheDocument();
    expect(screen.getByText('VS Code')).toBeInTheDocument();
  });

  it('invokes the callback with the chosen target', () => {
    const onOpenInIDE = vi.fn();
    renderRow(onOpenInIDE);
    fireEvent.click(screen.getByText('Cursor'));
    expect(onOpenInIDE).toHaveBeenCalledWith('chat-test-456', 'cursor');
  });

  it('hides the submenu when no handler is provided', () => {
    renderRow(undefined);
    expect(screen.queryByText('Open in IDE')).not.toBeInTheDocument();
  });
});
