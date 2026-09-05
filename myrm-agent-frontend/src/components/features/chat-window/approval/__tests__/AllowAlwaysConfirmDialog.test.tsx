import React, { useState } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AllowAlwaysConfirmDialog from '../AllowAlwaysConfirmDialog';
import type { AllowAlwaysDuration, AllowAlwaysScope } from '@/lib/approval/allowAlwaysScope';

vi.mock('next-intl', () => ({
  useTranslations: () => {
    const messages: Record<string, string> = {
      'allowAlwaysConfirm.title': 'Confirm Always Allow?',
      'allowAlwaysConfirm.description': 'Auto-approves future matching calls.',
      'allowAlwaysConfirm.warning': 'Security Risk Warning:',
      'allowAlwaysConfirm.risk1': 'Matching tools will run automatically',
      'allowAlwaysConfirm.risk2': 'Includes potentially risky operations',
      'allowAlwaysConfirm.risk3': 'Only use for trusted commands',
      'allowAlwaysConfirm.confirm': 'I understand the risks, proceed',
      'allowAlwaysConfirm.scopeLabel': 'Match Scope',
      'allowAlwaysConfirm.scopeTool': 'This Tool Only',
      'allowAlwaysConfirm.scopeExact': 'Exact Command',
      'allowAlwaysConfirm.scopePattern': 'Similar Commands',
      'allowAlwaysConfirm.scopePermission': 'All Tools of This Type',
      'allowAlwaysConfirm.scopeToolDesc': 'Auto-allow all future calls to tool',
      'allowAlwaysConfirm.scopeExactDesc': 'Only auto-allow exact match',
      'allowAlwaysConfirm.scopePatternDesc': 'Auto-allow starting same way',
      'allowAlwaysConfirm.scopePatternUnavailable': 'Pattern matching unavailable',
      'allowAlwaysConfirm.scopePermissionDesc': 'Auto-allow all in category',
      'allowAlwaysConfirm.durationLabel': 'Grant Duration',
      'allowAlwaysConfirm.durationSession': 'Current Session Only (Recommended)',
      'allowAlwaysConfirm.duration15m': '15 Minutes (Temporary Batch Run)',
      'allowAlwaysConfirm.duration1h': '1 Hour (Active Debugging)',
      'allowAlwaysConfirm.durationPermanent': 'Permanent (High Risk)',
      'allowAlwaysConfirm.durationSessionDesc': 'Auto-revokes when chat ends or refreshes.',
      'allowAlwaysConfirm.duration15mDesc': 'Skips approvals for 15 minutes.',
      'allowAlwaysConfirm.duration1hDesc': 'Skips approvals for 1 hour.',
      'allowAlwaysConfirm.durationPermanentDesc': 'Permanently bypasses approval.',
      'allowAlwaysConfirm.permanentRiskWarning': 'Warning: Permanent bypass leaves operation open indefinitely.',
      cancel: 'Cancel',
    };
    return (key: string) => messages[key] ?? key;
  },
}));

function TestWrapper(props: { initialDuration?: AllowAlwaysDuration; onConfirmMock?: () => void }) {
  const [open, setOpen] = useState(true);
  const [scope, setScope] = useState<AllowAlwaysScope>('exact');
  const [duration, setDuration] = useState<AllowAlwaysDuration>(props.initialDuration ?? 'session');

  return (
    <AllowAlwaysConfirmDialog
      open={open}
      onOpenChange={setOpen}
      allowAlwaysScope={scope}
      setAllowAlwaysScope={setScope}
      allowAlwaysDuration={duration}
      setAllowAlwaysDuration={setDuration}
      permissionTypeLabel="Code Execution"
      toolName="bash_code_execute_tool"
      shellCommand="echo hello"
      onConfirm={props.onConfirmMock ?? vi.fn()}
      isLoading={false}
    />
  );
}

describe('AllowAlwaysConfirmDialog Duration & Scope Gates', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders title, warnings, scope and duration selectors with session default', () => {
    render(<TestWrapper initialDuration="session" />);

    expect(screen.getByText('Confirm Always Allow?')).toBeInTheDocument();
    expect(screen.getByText('Grant Duration')).toBeInTheDocument();
    expect(screen.getByText('Current Session Only (Recommended)')).toBeInTheDocument();
    expect(screen.getByText('Auto-revokes when chat ends or refreshes.')).toBeInTheDocument();
  });

  it('shows permanent high-risk warning when duration is set to permanent', () => {
    render(<TestWrapper initialDuration="permanent" />);

    expect(screen.getByText('Permanent (High Risk)')).toBeInTheDocument();
    expect(screen.getByText('Permanently bypasses approval.')).toBeInTheDocument();
    expect(screen.getByText('Warning: Permanent bypass leaves operation open indefinitely.')).toBeInTheDocument();
  });

  it('triggers onConfirm when confirmation action button is clicked', () => {
    const handleConfirm = vi.fn();
    render(<TestWrapper onConfirmMock={handleConfirm} />);

    const confirmBtn = screen.getByRole('button', { name: 'I understand the risks, proceed' });
    fireEvent.click(confirmBtn);

    expect(handleConfirm).toHaveBeenCalledTimes(1);
  });
});
