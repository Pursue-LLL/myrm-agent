/** @vitest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { AgentMentionPopup } from '../AgentMentionPopup';
import type { GroupChatBotMember } from '../groupChatTypes';

const mockMembers: GroupChatBotMember[] = [
  {
    id: 'agent-arch',
    name: '架构总监',
    role: 'Architect',
    colorBadge: '#6366f1',
    status: 'idle',
    skills: ['system-design'],
    description: '顶层架构评审',
  },
  {
    id: 'agent-sec',
    name: '安全审计官',
    role: 'Security',
    colorBadge: '#f59e0b',
    status: 'pass',
    skills: ['sast-scan'],
    description: '安全合规拦截',
  },
  {
    id: 'agent-coder',
    name: '全栈执行官',
    role: 'Coder',
    colorBadge: '#10b981',
    status: 'reasoning',
    skills: ['typescript'],
  },
];

describe('AgentMentionPopup Component', () => {
  it('does not render when isOpen is false', () => {
    const { container } = render(
      <AgentMentionPopup
        isOpen={false}
        members={mockMembers}
        onSelectAgent={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders all members when open without filter', () => {
    render(
      <AgentMentionPopup
        isOpen={true}
        members={mockMembers}
        onSelectAgent={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByTestId('agent-mention-popup')).toBeDefined();
    expect(screen.getByText('架构总监')).toBeDefined();
    expect(screen.getByText('安全审计官')).toBeDefined();
    expect(screen.getByText('全栈执行官')).toBeDefined();
  });

  it('filters agents by mention text prefix (e.g. @sec)', () => {
    render(
      <AgentMentionPopup
        isOpen={true}
        filterText="@sec"
        members={mockMembers}
        onSelectAgent={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText('安全审计官')).toBeDefined();
    expect(screen.queryByText('架构总监')).toBeNull();
    expect(screen.queryByText('全栈执行官')).toBeNull();
  });

  it('selects agent on click and closes popup', () => {
    const onSelectMock = vi.fn();
    const onCloseMock = vi.fn();

    render(
      <AgentMentionPopup
        isOpen={true}
        members={mockMembers}
        onSelectAgent={onSelectMock}
        onClose={onCloseMock}
      />,
    );

    const optionBtn = screen.getByTestId('mention-option-agent-sec');
    fireEvent.click(optionBtn);

    expect(onSelectMock).toHaveBeenCalledWith(mockMembers[1]);
    expect(onCloseMock).toHaveBeenCalled();
  });

  it('supports keyboard navigation with ArrowDown, ArrowUp, and Enter', () => {
    const onSelectMock = vi.fn();
    const onCloseMock = vi.fn();

    render(
      <AgentMentionPopup
        isOpen={true}
        members={mockMembers}
        onSelectAgent={onSelectMock}
        onClose={onCloseMock}
      />,
    );

    const listbox = screen.getByTestId('agent-mention-popup');

    // Arrow down to second option (agent-sec)
    fireEvent.keyDown(listbox, { key: 'ArrowDown' });
    // Press enter
    fireEvent.keyDown(listbox, { key: 'Enter' });

    expect(onSelectMock).toHaveBeenCalledWith(mockMembers[1]);
    expect(onCloseMock).toHaveBeenCalled();
  });

  it('closes on Escape key press', () => {
    const onCloseMock = vi.fn();

    render(
      <AgentMentionPopup
        isOpen={true}
        members={mockMembers}
        onSelectAgent={vi.fn()}
        onClose={onCloseMock}
      />,
    );

    const listbox = screen.getByTestId('agent-mention-popup');
    fireEvent.keyDown(listbox, { key: 'Escape' });

    expect(onCloseMock).toHaveBeenCalled();
  });
});
