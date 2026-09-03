/**
 * Unit tests for ChatHistoryRow and useChatActions artifact reveal.
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
    'chat.revealArtifacts.action': 'Reveal Artifacts in Folder',
    'chat.revealArtifacts.revealing': 'Opening Folder...',
    'common.rename': 'Rename',
    'common.delete': 'Delete',
    'common.export': 'Export',
  };
  return dict[key] || key;
}) as any;

describe('ChatHistoryRow Artifact Reveal', () => {
  const dummyChat: ChatItem = {
    id: 'chat-test-123',
    title: 'Test Artifact Session',
    createdAt: new Date(),
    updatedAt: new Date(),
  };

  it('renders reveal artifacts menu item and triggers callback', () => {
    const onRevealArtifacts = vi.fn();

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
        onPin={vi.fn()}
        onUnpin={vi.fn()}
        onRevealArtifacts={onRevealArtifacts}
        t={mockT}
      />,
    );

    const revealItem = screen.getByText('Reveal Artifacts in Folder');
    expect(revealItem).toBeInTheDocument();

    fireEvent.click(revealItem);
    expect(onRevealArtifacts).toHaveBeenCalledWith('chat-test-123');
  });

  it('displays revealing state when in progress', () => {
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
        onPin={vi.fn()}
        onUnpin={vi.fn()}
        onRevealArtifacts={vi.fn()}
        isRevealingArtifacts={true}
        t={mockT}
      />,
    );

    const revealingItem = screen.getByText('Opening Folder...');
    expect(revealingItem).toBeInTheDocument();
  });
});
