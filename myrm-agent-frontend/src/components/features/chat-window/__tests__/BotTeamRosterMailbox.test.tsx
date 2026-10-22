import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  BotTeamRosterMailbox,
  BotProfileData,
  BotMessageData,
} from '../BotTeamRosterMailbox';

describe('BotTeamRosterMailbox', () => {
  const sampleBots: BotProfileData[] = [
    {
      bot_id: 'bot_arch',
      handle: '@architect',
      display_name: 'Lead Architect',
      role_description: 'System design and governance',
      model_tier: 'reasoning',
      status: 'idle',
      unread_count: 2,
    },
    {
      bot_id: 'bot_qa',
      handle: '@qa_tester',
      display_name: 'QA Engineer',
      role_description: 'Automated test suites',
      model_tier: 'fast',
      status: 'busy',
      active_task_id: 'task_run_101',
      unread_count: 0,
    },
  ];

  const sampleMessages: BotMessageData[] = [
    {
      message_id: 'msg_001',
      from_bot: '@qa_tester',
      to_bot: '@architect',
      subject: 'Regression test passed',
      body: 'All 15 suite cases passed in 2.3s.',
      priority: 'high',
      is_read: false,
      timestamp: '10:00 AM',
    },
    {
      message_id: 'msg_002',
      from_bot: '@orchestrator',
      to_bot: '@architect',
      subject: 'Architecture review request',
      body: 'Please verify Item 33 contracts.',
      priority: 'urgent',
      is_read: false,
      timestamp: '10:05 AM',
    },
  ];

  it('renders colleague roster list with status and unread badges', () => {
    render(
      <BotTeamRosterMailbox
        sessionId="chat_test_1"
        bots={sampleBots}
        inboxMessages={sampleMessages}
      />,
    );

    expect(screen.getByText('AI 同事花名册与工位信箱')).toBeInTheDocument();
    expect(screen.getByText('2 名成员')).toBeInTheDocument();
    expect(screen.getAllByText('Lead Architect').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('QA Engineer')).toBeInTheDocument();
    expect(screen.getByText('architect')).toBeInTheDocument();
    expect(screen.getByText('qa_tester')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument(); // Unread badge for architect
  });

  it('handles selecting a bot and invokes onSelectBot callback', () => {
    const handleSelect = vi.fn();
    render(
      <BotTeamRosterMailbox
        sessionId="chat_test_1"
        bots={sampleBots}
        onSelectBot={handleSelect}
      />,
    );

    const qaButton = screen.getByText('QA Engineer');
    fireEvent.click(qaButton);

    expect(handleSelect).toHaveBeenCalledWith('bot_qa');
  });

  it('renders active bot details, status badge, and inbox messages', () => {
    render(
      <BotTeamRosterMailbox
        sessionId="chat_test_1"
        bots={sampleBots}
        selectedBotId="bot_arch"
        inboxMessages={sampleMessages}
      />,
    );

    expect(screen.getByText('工位信箱收件 (2)')).toBeInTheDocument();
    expect(screen.getByText('Regression test passed')).toBeInTheDocument();
    expect(screen.getByText('Architecture review request')).toBeInTheDocument();
    expect(screen.getByText('紧急')).toBeInTheDocument();
    expect(screen.getByText('高')).toBeInTheDocument();
  });

  it('submits compose form and triggers onSendMessage callback', () => {
    const handleSend = vi.fn();
    render(
      <BotTeamRosterMailbox
        sessionId="chat_test_1"
        bots={sampleBots}
        selectedBotId="bot_arch"
        onSendMessage={handleSend}
      />,
    );

    // Click compose button to reveal form
    const composeBtn = screen.getByText('发信');
    fireEvent.click(composeBtn);

    expect(screen.getByPlaceholderText('主题 (Subject)...')).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('主题 (Subject)...'), {
      target: { value: 'Code Review Notice' },
    });
    fireEvent.change(screen.getByPlaceholderText('正文与参数任务描述...'), {
      target: { value: 'Please review Item 33 diff' },
    });

    const submitBtn = screen.getByRole('button', { name: '发送' });
    fireEvent.click(submitBtn);

    expect(handleSend).toHaveBeenCalledWith(
      '@architect',
      'Code Review Notice',
      'Please review Item 33 diff',
      'normal',
    );
  });

  it('submits mention broadcast and triggers onDispatchMentions callback', () => {
    const handleDispatch = vi.fn();
    render(
      <BotTeamRosterMailbox
        sessionId="chat_test_1"
        bots={sampleBots}
        onDispatchMentions={handleDispatch}
      />,
    );

    const mentionInput = screen.getByPlaceholderText('文本包含 @handle 自动广播寻址分发...');
    fireEvent.change(mentionInput, {
      target: { value: 'Ping @architect and @qa_tester for standup' },
    });

    const broadcastBtn = screen.getByRole('button', { name: /广播/ });
    fireEvent.click(broadcastBtn);

    expect(handleDispatch).toHaveBeenCalledWith('Ping @architect and @qa_tester for standup');
  });

  it('triggers onMarkRead when Mark All Read button is clicked', () => {
    const handleMarkRead = vi.fn();
    render(
      <BotTeamRosterMailbox
        sessionId="chat_test_1"
        bots={sampleBots}
        selectedBotId="bot_arch"
        inboxMessages={sampleMessages}
        onMarkRead={handleMarkRead}
      />,
    );

    const markAllBtn = screen.getByText('全部标为已读');
    fireEvent.click(markAllBtn);

    expect(handleMarkRead).toHaveBeenCalledWith('bot_arch', ['msg_001', 'msg_002']);
  });

  it('renders close button and triggers onClose callback', () => {
    const handleClose = vi.fn();
    render(
      <BotTeamRosterMailbox
        sessionId="chat_test_1"
        bots={sampleBots}
        onClose={handleClose}
      />,
    );

    const closeBtn = screen.getByLabelText('Close Bot Mode Panel');
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
