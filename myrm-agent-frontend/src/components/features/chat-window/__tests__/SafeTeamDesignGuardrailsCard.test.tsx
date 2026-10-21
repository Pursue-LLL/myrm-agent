import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  SafeTeamDesignGuardrailsCard,
  TeamScopeAuditData,
} from '../SafeTeamDesignGuardrailsCard';

describe('SafeTeamDesignGuardrailsCard', () => {
  const safeAuditSample: TeamScopeAuditData = {
    is_safe: true,
    sanitized_tools_map: {
      orchestrator: ['spawn_subagent', 'delegate_task'],
      coder: ['file_read', 'file_write', 'test_runner'],
    },
    violations: [],
    fanout_capped: false,
    original_member_count: 2,
    approved_member_count: 2,
    audit_summary: 'Squad design passed all scope guardrails. All 2 roles adhere to minimum necessary privileges.',
  };

  const triggeredAuditSample: TeamScopeAuditData = {
    is_safe: false,
    sanitized_tools_map: {
      researcher: ['web_search'],
      coder: ['file_read'],
    },
    violations: [
      {
        role_key: 'coder',
        tool_name: 'raw_bash_root',
        violation_type: 'forbidden_tool',
        severity: 'blocker',
        recommendation: "Tool 'raw_bash_root' is globally forbidden. Stripped from 'coder'.",
      },
      {
        role_key: 'researcher',
        tool_name: 'file_write',
        violation_type: 'role_scope_exceeded',
        severity: 'warning',
        recommendation: "Tool 'file_write' exceeds least-privilege allowlist for 'researcher'.",
      },
    ],
    fanout_capped: true,
    original_member_count: 7,
    approved_member_count: 5,
    audit_summary: 'Squad design flagged with 1 blocker(s) and 2 total violation(s). Sanitized fallback blueprint prepared.',
  };

  it('renders safe mode team design successfully with tools per role', () => {
    render(
      <SafeTeamDesignGuardrailsCard
        chatId="chat_safe_01"
        audit={safeAuditSample}
      />,
    );

    expect(screen.getByText(/Safe Team Design Guardrails/i)).toBeInTheDocument();
    expect(screen.getByText(/Safe Mode/i)).toBeInTheDocument();
    expect(screen.getByText(/2 of 2 Roles Active/i)).toBeInTheDocument();
    expect(screen.getByText(/orchestrator:/i)).toBeInTheDocument();
    expect(screen.getByText(/coder:/i)).toBeInTheDocument();
  });

  it('renders guardrail alerts, fanout cap alert, and scope violations', () => {
    render(
      <SafeTeamDesignGuardrailsCard
        chatId="chat_danger_02"
        audit={triggeredAuditSample}
      />,
    );

    expect(screen.getByText(/Guardrails Triggered/i)).toBeInTheDocument();
    expect(screen.getByText(/Fan-Out Cap Enforced:/i)).toBeInTheDocument();
    expect(screen.getByText(/5 of 7 Roles Active/i)).toBeInTheDocument();
    expect(screen.getByText(/Scope Violations \(1 Blockers, 1 Warnings\)/i)).toBeInTheDocument();
    expect(screen.getByText(/\[coder\] raw_bash_root/i)).toBeInTheDocument();
    expect(screen.getByText(/\[researcher\] file_write/i)).toBeInTheDocument();
  });

  it('triggers onAdoptSanitized callback when Adopt button is clicked', () => {
    const handleAdopt = vi.fn();

    render(
      <SafeTeamDesignGuardrailsCard
        chatId="chat_danger_02"
        audit={triggeredAuditSample}
        onAdoptSanitized={handleAdopt}
      />,
    );

    const adoptBtn = screen.getByRole('button', { name: /Adopt Sanitized Tools/i });
    fireEvent.click(adoptBtn);
    expect(handleAdopt).toHaveBeenCalledWith(triggeredAuditSample.sanitized_tools_map);
    expect(screen.getByText(/Sanitized Tools Adopted!/i)).toBeInTheDocument();
  });

  it('triggers onDismiss callback when close button is clicked', () => {
    const handleDismiss = vi.fn();

    render(
      <SafeTeamDesignGuardrailsCard
        chatId="chat_safe_01"
        audit={safeAuditSample}
        onDismiss={handleDismiss}
      />,
    );

    const closeBtn = screen.getByRole('button', { name: /Dismiss Guardrails Card/i });
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });
});
