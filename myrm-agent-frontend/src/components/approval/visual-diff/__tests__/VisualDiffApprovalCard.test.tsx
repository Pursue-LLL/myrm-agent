/**
 * [INPUT]
 * VisualDiffApprovalCard, StructuredApprovalRequest, ApprovalNotificationBridge
 * [OUTPUT]
 * Comprehensive unit tests covering visual diff rendering, command risk radar, hotkeys, and notification bridge.
 * [POS]
 * src/components/approval/visual-diff/__tests__/VisualDiffApprovalCard.test.tsx
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { VisualDiffApprovalCard } from '../VisualDiffApprovalCard';
import { ApprovalNotificationBridge } from '../ApprovalNotificationBridge';
import { StructuredApprovalRequest } from '../visualDiffTypes';

describe('VisualDiffApprovalCard', () => {
  const mockFileDiffRequest: StructuredApprovalRequest = {
    approval_id: 'appr-file-001',
    session_id: 'sess-code-review',
    sequence_id: 1,
    kind: 'file_write',
    summary: "Modify src/core/engine.ts (+2 / -1)",
    file_diff: {
      file_path: 'src/core/engine.ts',
      old_content: 'const a = 1;\n',
      new_content: 'const a = 1;\nconst b = 2;\nconst c = 3;\n',
      unified_diff: '--- a/src/core/engine.ts\n+++ b/src/core/engine.ts\n@@ -1,1 +1,3 @@\n const a = 1;\n+const b = 2;\n+const c = 3;',
      added_lines: 2,
      removed_lines: 1,
      is_new_file: false,
      is_deletion: false,
    },
    command_risk: null,
    created_at: 1760000000,
    expires_at: 1760000300,
    allowed_decisions: ['allow', 'reject', 'remember_session'],
  };

  const mockCommandRequest: StructuredApprovalRequest = {
    approval_id: 'appr-cmd-002',
    session_id: 'sess-cmd-eval',
    sequence_id: 2,
    kind: 'command_exec',
    summary: 'Destructive deletion: rm -rf /tmp/cache',
    file_diff: null,
    command_risk: {
      command: 'rm -rf /tmp/cache',
      cwd: '/workspace',
      risk_severity: 'critical',
      risk_reasons: ['Recursive file deletion within system cache directory'],
      blast_radius_paths: ['/tmp/cache', '/workspace'],
    },
    created_at: 1760000000,
    expires_at: 1760000300,
    allowed_decisions: ['allow', 'reject'],
  };

  it('renders file modification diff with added and removed line counts', () => {
    const onDecision = vi.fn();
    render(<VisualDiffApprovalCard request={mockFileDiffRequest} onDecision={onDecision} />);

    expect(screen.getByTestId('visual-diff-approval-card')).toBeDefined();
    expect(screen.getByTestId('file-diff-section')).toBeDefined();
    expect(screen.getByText('src/core/engine.ts')).toBeDefined();
    expect(screen.getByTestId('diff-lines-added')).toBeDefined();
    expect(screen.getByText('+2')).toBeDefined();
    expect(screen.getByTestId('diff-lines-removed')).toBeDefined();
    expect(screen.getByText('-1')).toBeDefined();
    expect(screen.getByTestId('unified-diff-view')).toBeDefined();
    expect(screen.getByText('+const b = 2;')).toBeDefined();
  });

  it('renders command risk radar with critical badge and blast radius', () => {
    const onDecision = vi.fn();
    render(<VisualDiffApprovalCard request={mockCommandRequest} onDecision={onDecision} />);

    expect(screen.getByTestId('command-risk-section')).toBeDefined();
    expect(screen.getByTestId('risk-badge-critical')).toBeDefined();
    expect(screen.getByText('Critical Risk')).toBeDefined();
    expect(screen.getByText('rm -rf /tmp/cache')).toBeDefined();
    expect(screen.getByText('/tmp/cache')).toBeDefined();
    expect(screen.getByText('/workspace')).toBeDefined();
    expect(
      screen.getByText('Recursive file deletion within system cache directory')
    ).toBeDefined();
  });

  it('triggers decisions via button clicks', () => {
    const onDecision = vi.fn();
    render(<VisualDiffApprovalCard request={mockFileDiffRequest} onDecision={onDecision} />);

    const allowBtn = screen.getByTestId('decision-allow-btn');
    fireEvent.click(allowBtn);
    expect(onDecision).toHaveBeenCalledWith('allow');

    const rejectBtn = screen.getByTestId('decision-reject-btn');
    fireEvent.click(rejectBtn);
    expect(onDecision).toHaveBeenCalledWith('reject');

    const rememberBtn = screen.getByTestId('decision-remember-btn');
    fireEvent.click(rememberBtn);
    expect(onDecision).toHaveBeenCalledWith('remember_session');
  });

  it('triggers decisions via keyboard hotkeys: 1/y for allow, 2/n for reject, 3 for remember', () => {
    const onDecision = vi.fn();
    render(
      <VisualDiffApprovalCard
        request={mockFileDiffRequest}
        onDecision={onDecision}
        isFocused={true}
      />
    );

    // Test 1 key
    fireEvent.keyDown(window, { key: '1' });
    expect(onDecision).toHaveBeenCalledWith('allow');

    // Test y key
    fireEvent.keyDown(window, { key: 'y' });
    expect(onDecision).toHaveBeenCalledWith('allow');

    // Test 2 key
    fireEvent.keyDown(window, { key: '2' });
    expect(onDecision).toHaveBeenCalledWith('reject');

    // Test n key
    fireEvent.keyDown(window, { key: 'n' });
    expect(onDecision).toHaveBeenCalledWith('reject');

    // Test 3 key
    fireEvent.keyDown(window, { key: '3' });
    expect(onDecision).toHaveBeenCalledWith('remember_session');
  });

  it('dispatches native notification via ApprovalNotificationBridge', async () => {
    const sendNotificationMock = vi.fn();
    // Mock window.__TAURI__
    (window as unknown as { __TAURI__?: unknown }).__TAURI__ = {
      notification: {
        sendNotification: sendNotificationMock,
      },
    };

    const notified = await ApprovalNotificationBridge.notifyApprovalRequired(mockCommandRequest);
    expect(notified).toBe(true);
    expect(sendNotificationMock).toHaveBeenCalledWith({
      title: 'Myrmidon Action Approval Required',
      body: 'Destructive deletion: rm -rf /tmp/cache [Press 1 to Allow, 2 to Reject]',
    });

    delete (window as unknown as { __TAURI__?: unknown }).__TAURI__;
  });
});
