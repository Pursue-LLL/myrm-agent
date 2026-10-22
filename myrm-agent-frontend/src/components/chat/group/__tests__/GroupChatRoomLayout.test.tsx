/** @vitest-environment jsdom */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { GroupChatRoomLayout } from '../GroupChatRoomLayout';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    title: 'Bot Mode 多 Agent 协同群聊工作区',
    hermesParity: '对标 Hermes v0.21.0 Bot Mode 与 hermes peer 点对点私信',
    roomsTitle: '协同工作频道',
    createRoom: '创建新房间',
    composerPlaceholder: '输入协作指令，按 @ 呼叫特定 Agent...',
    sendBtn: '发送',
    noMessages: '暂无群聊消息',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('GroupChatRoomLayout', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(window.HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
  });

  it('renders room header, Bot Mode badge, and Hermes parity label', async () => {
    render(<GroupChatRoomLayout />);

    await waitFor(() => {
      expect(screen.getByText('Engineering War Room')).toBeInTheDocument();
    });

    expect(screen.getByText('Bot Mode')).toBeInTheDocument();
    expect(screen.getByText('Hermes Parity')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('输入协作指令，按 @ 呼叫特定 Agent...')).toBeInTheDocument();
  });

  it('renders participants and canonical inbox in sidebar', async () => {
    render(<GroupChatRoomLayout />);

    await waitFor(() => {
      expect(screen.getByText('Room Participants (3)')).toBeInTheDocument();
    });

    expect(screen.getByText('You (Operator)')).toBeInTheDocument();
    expect(screen.getAllByText('Code Architect').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Test Runner').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Canonical Peer Inbox')).toBeInTheDocument();
  });

  it('displays initial room message on the timeline', async () => {
    render(<GroupChatRoomLayout />);

    await waitFor(() => {
      expect(screen.getByText(/Multi-agent room initialized/i)).toBeInTheDocument();
    });
  });

  it('opens mention dropdown when typing @ and appends mention into input', async () => {
    render(<GroupChatRoomLayout />);

    await waitFor(() => {
      expect(screen.getByText('Engineering War Room')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('输入协作指令，按 @ 呼叫特定 Agent...');
    fireEvent.change(input, { target: { value: 'Hey @' } });

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    const option = screen.getByText('@Code Architect');
    fireEvent.click(option);

    expect(input).toHaveValue('Hey @Code Architect ');
  });

  it('sends user message and dispatches bot collaborative reply', async () => {
    render(<GroupChatRoomLayout />);

    await waitFor(() => {
      expect(screen.getByText('Engineering War Room')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('输入协作指令，按 @ 呼叫特定 Agent...');
    fireEvent.change(input, { target: { value: 'Review @Code Architect' } });

    const form = screen.getByTestId('group-chat-composer-form');
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText('Review @Code Architect')).toBeInTheDocument();
      expect(screen.getByText(/Received mission/i)).toBeInTheDocument();
    });
  });
});
