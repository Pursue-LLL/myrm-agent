/** @vitest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { GroupChatRoomHeader } from '../GroupChatRoomHeader';
import type { GroupChatBotMember } from '../groupChatTypes';

const mockMembers: GroupChatBotMember[] = [
  {
    id: 'agent-arch',
    name: '架构总监',
    role: 'Architect',
    colorBadge: '#6366f1',
    status: 'idle',
    skills: ['system-design', 'security-audit'],
    description: '负责系统顶层架构演进与模式评审',
  },
  {
    id: 'agent-coder',
    name: '全栈专家',
    role: 'Coder',
    colorBadge: '#10b981',
    status: 'reasoning',
    skills: ['typescript', 'python', 'docker'],
    description: '负责高并发业务逻辑编写与单测驱动开发',
  },
  {
    id: 'agent-qa',
    name: '安全审计官',
    role: 'Security',
    colorBadge: '#f59e0b',
    status: 'pass',
    skills: ['sast-scan', 'dependency-check'],
    description: '负责代码合规与安全漏洞阻断',
  },
];

describe('GroupChatRoomHeader Component', () => {
  it('renders room title, members count and status indicators', () => {
    render(
      <GroupChatRoomHeader
        roomName="敏捷全栈战情室"
        members={mockMembers}
      />,
    );

    expect(screen.getByText('敏捷全栈战情室')).toBeDefined();
    expect(screen.getByText('3')).toBeDefined();

    expect(screen.getByTestId('status-indicator-idle')).toBeDefined();
    expect(screen.getByTestId('status-indicator-reasoning')).toBeDefined();
    expect(screen.getByTestId('status-indicator-pass')).toBeDefined();
  });

  it('inspects member details and skills on avatar click', () => {
    const onSelectMemberMock = vi.fn();

    render(
      <GroupChatRoomHeader
        roomName="敏捷全栈战情室"
        members={mockMembers}
        onSelectMember={onSelectMemberMock}
      />,
    );

    const coderBtn = screen.getByTestId('member-avatar-agent-coder');
    fireEvent.click(coderBtn);

    expect(onSelectMemberMock).toHaveBeenCalledWith(mockMembers[1]);
    expect(screen.getByTestId('member-inspect-panel')).toBeDefined();
    expect(screen.getByText('typescript')).toBeDefined();
    expect(screen.getByText('python')).toBeDefined();

    // Close panel
    const closeBtn = screen.getByRole('button', { name: '关闭' });
    fireEvent.click(closeBtn);

    expect(screen.queryByTestId('member-inspect-panel')).toBeNull();
  });
});
