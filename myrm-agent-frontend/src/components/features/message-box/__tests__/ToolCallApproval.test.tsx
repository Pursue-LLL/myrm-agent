'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ToolCallApproval from '@/components/features/message-box/ToolCallApproval';
import type { ToolCallInfo } from '@/store/chat/types';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, string | number>) => {
    const dict: Record<string, Record<string, string>> = {
      toolApproval: {
        approve: 'Approve',
        reject: 'Reject',
        'saveSkill.approve': 'Add to my skills',
        'saveSkill.deny': 'Not now',
        'saveSkill.showFullInstructions': 'Show full',
        'saveSkill.showLess': 'Show less',
        'saveSkill.showAllLines': 'Show all {count} lines',
        'saveSkill.footer': 'Footer',
        executionIntent: 'Agent intent',
        'toolCallStatus.pending': 'Pending approval',
        'toolCallStatus.approved': 'Approved',
        'toolCallStatus.rejected': 'Rejected',
        'toolCallStatus.completed': 'Completed',
        toolCallPendingBanner: '{count} awaiting',
        'ptc.readOnlyLabel': 'Read-Only',
        'ptc.readOnlyTitle': 'Read only hint',
        'ptc.destructiveLabel': 'Destructive',
        'ptc.destructiveTitle': 'Destructive hint',
        'ptc.openWorldLabel': 'Open World',
        'ptc.openWorldTitle': 'Open world hint',
      },
      humanize: {
        'approval.save_skill': 'Add skill: {name}',
        'scope.local': 'Changes stay on this device',
        'scope.external': 'Sends data to {destination}',
        'scope.external_unknown': 'an external service',
      },
    };
    let out = dict[namespace]?.[key] ?? `${namespace}.${key}`;
    if (values) {
      for (const [k, v] of Object.entries(values)) {
        out = out.replace(`{${k}}`, String(v));
      }
    }
    return out;
  },
}));

const pendingToolCall: ToolCallInfo = {
  callId: 'call-1',
  toolName: 'skill_manage_tool',
  arguments: {
    action: 'save',
    name: 'weekly-digest',
    content: '# Weekly digest',
  },
  status: 'pending',
  requiresApproval: true,
};

describe('ToolCallApproval i18n', () => {
  it('renders localized status badge instead of hardcoded Chinese', () => {
    render(
      <ToolCallApproval
        toolCalls={[pendingToolCall]}
        chatId="chat-1"
        onApprove={async () => {}}
        onReject={async () => {}}
      />,
    );

    expect(screen.getByText('Pending approval')).toBeInTheDocument();
    expect(screen.queryByText('待审批')).not.toBeInTheDocument();
    expect(screen.getByText('1 awaiting')).toBeInTheDocument();
  });

  it('renders localized scope note under the tool title', () => {
    render(
      <ToolCallApproval
        toolCalls={[{ ...pendingToolCall, toolName: 'file_write_tool', arguments: { path: '/tmp/a.md' } }]}
        chatId="chat-1"
        onApprove={async () => {}}
        onReject={async () => {}}
      />,
    );

    expect(screen.getByText('Changes stay on this device')).toBeInTheDocument();
  });

  it('renders localized PTC badges', () => {
    render(
      <ToolCallApproval
        toolCalls={[
          {
            ...pendingToolCall,
            toolName: 'mcp__demo__read_tool',
            arguments: {},
            ptcAnnotations: { readOnlyHint: true },
          },
        ]}
        chatId="chat-1"
        onApprove={async () => {}}
        onReject={async () => {}}
      />,
    );

    expect(screen.getByText('Read-Only')).toBeInTheDocument();
    expect(screen.queryByText('待审批')).not.toBeInTheDocument();
  });
});
