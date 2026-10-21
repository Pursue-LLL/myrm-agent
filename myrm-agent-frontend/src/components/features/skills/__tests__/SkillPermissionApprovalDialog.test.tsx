/** @vitest-environment jsdom */

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SkillPermissionApprovalDialog } from '../SkillPermissionApprovalDialog';
import type { SkillPermissionRequest, PermissionTemplateType } from '../SkillPermissionApprovalDialog';

const TRANSLATIONS: Record<string, string> = {
  approvalTitle: 'Skill Permission Approval',
  approvalDescription: 'This skill needs the following permissions',
  skillName: 'Skill Name',
  'template.label': 'Use a permission template',
  'template.placeholder': 'Select a standard template',
  'template.none': 'No template',
  'template.readonly': 'Read-Only',
  'template.dataAnalysis': 'Data Analysis',
  'template.webAutomation': 'Web Automation',
  'template.developerTools': 'Developer Tools',
  'template.systemAdmin': 'System Admin (Dangerous)',
  'template.hint': 'Template will auto-select permissions',
  dangerousPermissions: 'Dangerous Permissions',
  dangerous: 'Dangerous',
  normalPermissions: 'Normal Permissions',
  networkAccess: 'Network Whitelist',
  allowedDomains: 'Allowed Domains',
  allowedDomainsDesc: 'Only these domains are allowed',
  dangerousWarning: 'This skill requests dangerous permissions',
  deny: 'Deny',
  approveAnyway: 'Approve Anyway',
  approve: 'Approve',
  'types.fileRead.label': 'Read Files',
  'types.fileWrite.label': 'Write Files',
  'types.fileDelete.label': 'Delete Files',
  'types.shellExec.label': 'Run Shell Commands',
  'types.codeInterpreter.label': 'Execute Code',
  'types.networkAccess.label': 'Network Access',
  'types.envVarAccess.label': 'Environment Variables',
};

const stableT = (key: string, values?: Record<string, string | number>): string => {
  let text = TRANSLATIONS[key] ?? key;
  if (values) {
    for (const [k, v] of Object.entries(values)) {
      text = text.replaceAll(`{${k}}`, String(v));
    }
  }
  return text;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/primitives/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) => (open ? <div>{children}</div> : null),
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({
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
}));

vi.mock('@/components/primitives/badge', () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

vi.mock('@/components/primitives/alert', () => ({
  Alert: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const selectState = vi.hoisted(() => ({
  onValueChange: undefined as undefined | ((value: string) => void),
}));

vi.mock('@/components/primitives/select', () => ({
  Select: ({ children, onValueChange }: { children: React.ReactNode; onValueChange?: (value: string) => void }) => {
    selectState.onValueChange = onValueChange;
    return <div>{children}</div>;
  },
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => null,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => (
    <button type="button" data-testid={`template-${value}`} onClick={() => selectState.onValueChange?.(value)}>
      {children}
    </button>
  ),
}));

const baseRequest: SkillPermissionRequest = {
  skillId: 'demo-skill',
  skillName: 'Demo Skill',
  description: 'A demo skill',
  requiredPermissions: ['file_read', 'shell_exec'],
};

describe('SkillPermissionApprovalDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders dangerous and normal permission groups', () => {
    render(
      <SkillPermissionApprovalDialog
        open
        request={baseRequest}
        onOpenChange={vi.fn()}
        onApprove={vi.fn()}
        onDeny={vi.fn()}
      />,
    );

    expect(screen.getByText('Dangerous Permissions')).toBeInTheDocument();
    expect(screen.getByText('Normal Permissions')).toBeInTheDocument();
    expect(screen.getByText('Run Shell Commands')).toBeInTheDocument();
    expect(screen.getByText('Read Files')).toBeInTheDocument();
    expect(screen.getByText('This skill requests dangerous permissions')).toBeInTheDocument();
  });

  it('approves without any always-allow argument', () => {
    const onApprove = vi.fn();
    render(
      <SkillPermissionApprovalDialog
        open
        request={baseRequest}
        onOpenChange={vi.fn()}
        onApprove={onApprove}
        onDeny={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText('Approve Anyway'));
    expect(onApprove).toHaveBeenCalledTimes(1);
    expect(onApprove).toHaveBeenCalledWith(undefined);
  });

  it('passes the selected template to onApprove', () => {
    const onApprove = vi.fn();
    render(
      <SkillPermissionApprovalDialog
        open
        request={{ ...baseRequest, requiredPermissions: ['file_read'] }}
        onOpenChange={vi.fn()}
        onApprove={onApprove}
        onDeny={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId('template-data_analysis'));
    fireEvent.click(screen.getByText('Approve'));
    expect(onApprove).toHaveBeenCalledTimes(1);
    expect(onApprove).toHaveBeenCalledWith('data_analysis' as PermissionTemplateType);
  });

  it('denies the request', () => {
    const onDeny = vi.fn();
    render(
      <SkillPermissionApprovalDialog
        open
        request={baseRequest}
        onOpenChange={vi.fn()}
        onApprove={vi.fn()}
        onDeny={onDeny}
      />,
    );

    fireEvent.click(screen.getByText('Deny'));
    expect(onDeny).toHaveBeenCalledTimes(1);
  });

  it('does not render the removed always-allow controls', () => {
    const safeRequest: SkillPermissionRequest = {
      ...baseRequest,
      requiredPermissions: ['file_read'],
    };
    render(
      <SkillPermissionApprovalDialog
        open
        request={safeRequest}
        onOpenChange={vi.fn()}
        onApprove={vi.fn()}
        onDeny={vi.fn()}
      />,
    );

    expect(screen.queryByText('Always allow permission requests from this skill')).not.toBeInTheDocument();
    expect(screen.queryByText('Allow All')).not.toBeInTheDocument();
    expect(screen.queryByTestId('always-allow-skill')).not.toBeInTheDocument();
  });

  it('renders nothing when request is null', () => {
    const { container } = render(
      <SkillPermissionApprovalDialog open request={null} onOpenChange={vi.fn()} onApprove={vi.fn()} onDeny={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
