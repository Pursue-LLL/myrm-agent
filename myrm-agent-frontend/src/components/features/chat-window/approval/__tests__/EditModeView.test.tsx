import React, { useState } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import EditModeView from '../EditModeView';
import type { AllowAlwaysDuration, AllowAlwaysScope } from '@/lib/approval/allowAlwaysScope';

vi.mock('next-intl', () => ({
  useTranslations: () => {
    const messages: Record<string, string> = {
      editTitle: 'Edit Command & Arguments',
      confirmEdit: 'Confirm & Run Edited',
      cancel: 'Cancel',
      allowAlwaysAfterEdit: 'Remember and allow future matching calls',
      'allowAlwaysConfirm.scopeExact': 'Exact Command',
      'allowAlwaysConfirm.scopePattern': 'Similar Commands',
      'allowAlwaysConfirm.scopeTool': 'This Tool Only',
      'allowAlwaysConfirm.scopePermission': 'All Tools of This Type',
      'allowAlwaysConfirm.scopeExactDesc': 'Only auto-allow exact match',
      'allowAlwaysConfirm.scopePatternDesc': 'Auto-allow starting same way',
      'allowAlwaysConfirm.scopeToolDesc': 'Auto-allow all future calls to tool',
      'allowAlwaysConfirm.scopePermissionDesc': 'Auto-allow all in category',
      'allowAlwaysConfirm.scopePatternUnavailable': 'Pattern matching unavailable',
      'allowAlwaysConfirm.durationSession': 'Current Session Only (Recommended)',
      'allowAlwaysConfirm.duration15m': '15 Minutes (Temporary Batch Run)',
      'allowAlwaysConfirm.duration1h': '1 Hour (Active Debugging)',
      'allowAlwaysConfirm.durationPermanent': 'Permanent (High Risk)',
      'allowAlwaysConfirm.durationSessionDesc': 'Auto-revokes when chat ends or refreshes.',
      'allowAlwaysConfirm.duration15mDesc': 'Skips approvals for 15 minutes.',
      'allowAlwaysConfirm.duration1hDesc': 'Skips approvals for 1 hour.',
      'allowAlwaysConfirm.durationPermanentDesc': 'Permanently bypasses approval.',
    };
    return (key: string, params?: Record<string, string>) => {
      let msg = messages[key] ?? key;
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          msg = msg.replace(`{${k}}`, v);
        });
      }
      return msg;
    };
  },
}));

function EditModeTestWrapper(props: {
  initialAllowAlways?: boolean;
  initialDuration?: AllowAlwaysDuration;
  onConfirmMock?: () => void;
  onCancelMock?: () => void;
}) {
  const [editedArgs, setEditedArgs] = useState<Record<string, string>>({ command: 'ls -la' });
  const [allowAlways, setAllowAlways] = useState(props.initialAllowAlways ?? true);
  const [scope, setScope] = useState<AllowAlwaysScope>('exact');
  const [duration, setDuration] = useState<AllowAlwaysDuration>(props.initialDuration ?? 'session');

  return (
    <EditModeView
      editedArgs={editedArgs}
      setEditedArgs={setEditedArgs}
      inputEntries={[['command', 'ls -la']]}
      isSingleStringParam={true}
      editValidationErrors={[]}
      allowAlwaysInEdit={allowAlways}
      setAllowAlwaysInEdit={setAllowAlways}
      allowAlwaysScopeInEdit={scope}
      setAllowAlwaysScopeInEdit={setScope}
      allowAlwaysDurationInEdit={duration}
      setAllowAlwaysDurationInEdit={setDuration}
      permissionTypeLabel="Terminal Execution"
      toolName="bash"
      shellCommand="ls -la"
      requestId="req-test-123"
      onConfirm={props.onConfirmMock ?? vi.fn()}
      onCancel={props.onCancelMock ?? vi.fn()}
      isLoading={false}
    />
  );
}

describe('EditModeView Duration & Scope Gates', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders duration selector and description when allowAlwaysInEdit is active', () => {
    render(<EditModeTestWrapper initialAllowAlways={true} initialDuration="session" />);

    expect(screen.getByText('Remember and allow future matching calls')).toBeInTheDocument();
    expect(screen.getByText('Current Session Only (Recommended)')).toBeInTheDocument();
    expect(screen.getByText('Auto-revokes when chat ends or refreshes.')).toBeInTheDocument();
  });

  it('renders different duration description when duration is 15m', () => {
    render(<EditModeTestWrapper initialAllowAlways={true} initialDuration="15m" />);

    expect(screen.getByText('15 Minutes (Temporary Batch Run)')).toBeInTheDocument();
    expect(screen.getByText('Skips approvals for 15 minutes.')).toBeInTheDocument();
  });

  it('triggers onConfirm when confirm button is clicked', () => {
    const handleConfirm = vi.fn();
    render(<EditModeTestWrapper onConfirmMock={handleConfirm} />);

    const confirmBtn = screen.getByRole('button', { name: 'Confirm & Run Edited' });
    fireEvent.click(confirmBtn);

    expect(handleConfirm).toHaveBeenCalledTimes(1);
  });
});
