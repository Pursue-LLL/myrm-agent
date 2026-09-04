'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SingleApprovalCard from '@/components/features/chat-window/SingleApprovalCard';
import type { ToolApprovalRequest } from '@/store/chat/types';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, string | number>) => {
    const dict: Record<string, Record<string, string>> = {
      toolApproval: {
        'saveSkill.approve': 'Add to my skills',
        'saveSkill.deny': 'Not now',
        'saveSkill.showFullInstructions': 'Show full instructions',
        'saveSkill.showLess': 'Show less',
        'saveSkill.showAllLines': 'Show all {count} lines',
        'saveSkill.footer': 'Footer copy',
        approve: 'Approve',
        reject: 'Reject',
        edit: 'Edit',
        expiresIn: 'Expires in {seconds}s',
        'permissionTypes.default': 'Tool',
      },
      humanize: {
        'approval.save_skill': 'Add skill: {name}',
        'scope.save_skill': 'Saves to Settings ▸ Skills',
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

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('@/store/useDesktopInspectorStore', () => ({
  default: (selector: (state: { viewData: null }) => unknown) => selector({ viewData: null }),
  selectScopedDesktopViewData: () => null,
}));

vi.mock('@/store/useBrowserInspectorStore', () => ({
  default: (selector: (state: { viewData: null }) => unknown) => selector({ viewData: null }),
  selectScopedBrowserViewData: () => null,
}));

const saveSkillRequest: ToolApprovalRequest = {
  requestId: 'req-save-skill',
  toolName: 'skill_manage_tool',
  toolInput: {
    action: 'save',
    name: 'weekly-digest',
    description: 'Weekly digest skill',
    content: '# Weekly digest\nCollect metrics',
  },
  reason: '',
  timeoutSeconds: 120,
  expiresAt: Math.floor(Date.now() / 1000) + 120,
  timeoutBehavior: 'deny',
  messageId: 'msg-1',
  displayMode: 'approval',
  chatId: 'chat-1',
  actionMode: 'agent',
};

describe('SingleApprovalCard save_skill', () => {
  it('renders SaveSkillApprovalPreview and custom approve/deny labels', () => {
    render(<SingleApprovalCard request={saveSkillRequest} onResolve={async () => {}} isLoading={false} />);

    expect(screen.getByTestId('save-skill-approval-preview')).toBeInTheDocument();
    expect(screen.getByText('Weekly digest skill')).toBeInTheDocument();
    expect(screen.getByText(/Collect metrics/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add to my skills' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Not now' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.queryByText(/"action"/)).not.toBeInTheDocument();
  });

  it('renders time-bound allow always trigger for regular tools', () => {
    const regularShellRequest: ToolApprovalRequest = {
      ...saveSkillRequest,
      requestId: 'req-shell',
      toolName: 'bash_code_execute_tool',
      toolInput: { command: 'npm run test' },
    };

    render(<SingleApprovalCard request={regularShellRequest} onResolve={async () => {}} isLoading={false} />);
    expect(screen.getByText('toolApproval.allowAlways')).toBeInTheDocument();
  });
});
