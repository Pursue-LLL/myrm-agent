import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PolymorphicApprovalCard } from '../PolymorphicApprovalCard';
import type { ApprovalPayload } from '@/store/useApprovalStore';

// Stable mock references to prevent infinite re-rendering and pass CI stability gate
const stableT = (key: string) => {
  const dict: Record<string, string> = {
    title: '不可逆破坏性操作硬阻断红线',
    description: '此操作包含递归强删、Git 破坏性覆写或底层设备抹除。严禁自动放行，需显式二次确认。',
    blastRadiusLabel: '影响爆炸半径',
    snapshotReady: '已创建影子版本快照',
    snapshotNone: '非 Git 仓库，无版本快照保护，操作不可撤销',
    confirmPrompt: '请输入 CONFIRM 确认执行破坏性操作',
    confirmButton: '确认执行破坏性操作',
    'irreversibleDestructive.title': '不可逆破坏性操作硬阻断红线',
    'irreversibleDestructive.description': '此操作包含递归强删、Git 破坏性覆写或底层设备抹除。严禁自动放行，需显式二次确认。',
    'irreversibleDestructive.confirmButton': '确认执行破坏性操作',
    approve: 'Approve',
    reject: 'Reject',
    allowAlways: 'Allow Always',
    commentsOptional: 'Comments (Optional)',
    addCommentPlaceholder: 'Add a comment...',
    executionIntent: 'Execution Intent',
  };
  return dict[key] || key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'zh',
}));

vi.mock('next-themes', () => ({
  useTheme: () => ({ resolvedTheme: 'light' }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe('PolymorphicApprovalCard Destructive Hard Stop', () => {
  it('renders destructive banner, hides allowAlways, and requires CONFIRM input before enabling approval', () => {
    const mockOnResolve = vi.fn().mockResolvedValue(undefined);
    const approval: ApprovalPayload = {
      approval_id: 'app_dest_1',
      user_id: 'usr_1',
      action_type: 'subagent_approval',
      status: 'pending',
      severity: 'high',
      payload: {
        tool_calls: [{ name: 'bash_code_execute_tool', args: { command: 'rm -rf /workspace/project' } }],
        reviewConfigs: [
          {
            irreversibleDestructive: true,
            hideAllowAlways: true,
            blastRadius: {
              command: 'rm -rf /workspace/project',
              impact_scope: 'critical_system_or_repo',
              summary_reason: '递归删除指定路径',
              affected_targets: ['/workspace/project'],
            },
            snapshotId: 'commit_hash_1234567890abcdef',
          },
        ],
      },
    };

    render(<PolymorphicApprovalCard approval={approval} onResolve={mockOnResolve} isSubmitting={false} />);

    // 1. Verify destructive banner is displayed
    expect(screen.getByText('不可逆破坏性操作硬阻断红线')).toBeDefined();
    expect(screen.getByText('递归删除指定路径')).toBeDefined();
    expect(screen.getByText('/workspace/project')).toBeDefined();
    expect(screen.getByText('critical_system_or_repo')).toBeDefined();

    // 2. Verify snapshot id is displayed
    expect(screen.getByText('已创建影子版本快照:')).toBeDefined();

    // 3. Verify allowAlways is physically hidden
    expect(screen.queryByText('Allow Always')).toBeNull();

    // 4. Verify approve button is initially disabled
    const approveBtn = screen.getByText('确认执行破坏性操作') as HTMLButtonElement;
    expect(approveBtn.disabled).toBe(true);

    // 5. User types invalid text
    const input = screen.getByPlaceholderText('CONFIRM') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'yes' } });
    expect(approveBtn.disabled).toBe(true);

    // 6. User types exact 'CONFIRM'
    fireEvent.change(input, { target: { value: 'CONFIRM' } });
    expect(approveBtn.disabled).toBe(false);

    // 7. Click confirm button
    fireEvent.click(approveBtn);
    expect(mockOnResolve).toHaveBeenCalledTimes(1);
    expect(mockOnResolve).toHaveBeenCalledWith('approve', '', undefined, expect.any(Object));
  });
});
