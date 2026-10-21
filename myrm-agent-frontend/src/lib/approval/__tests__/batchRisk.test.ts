import { describe, it, expect } from 'vitest';
import { classifyBatchApprovalRisk, classifySingleApprovalRisk } from '../batchRisk';
import type { ApprovalPayload } from '@/store/useApprovalStore';

describe('batchRisk classification logic', () => {
  it('correctly classifies safe approvals', () => {
    const item: ApprovalPayload = {
      approval_id: 'appr-1',
      user_id: 'u1',
      action_type: 'read_file',
      status: 'PENDING',
      severity: 'info',
    };
    const res = classifySingleApprovalRisk(item);
    expect(res.riskLevel).toBe('safe');
  });

  it('correctly classifies high risk when severity is critical', () => {
    const item: ApprovalPayload = {
      approval_id: 'appr-2',
      user_id: 'u1',
      action_type: 'custom_op',
      status: 'PENDING',
      severity: 'critical',
      reason: 'Root access requested',
    };
    const res = classifySingleApprovalRisk(item);
    expect(res.riskLevel).toBe('high');
    expect(res.reason).toBe('Root access requested');
  });

  it('correctly classifies smartDenied in reviewConfigs', () => {
    const item: ApprovalPayload = {
      approval_id: 'appr-3',
      user_id: 'u1',
      action_type: 'subagent_approval',
      status: 'PENDING',
      severity: 'info',
      payload: {
        reviewConfigs: [{ smartDenied: true }],
      },
    };
    const res = classifySingleApprovalRisk(item);
    expect(res.riskLevel).toBe('high');
  });

  it('correctly classifies isSpend as high risk to prevent financial accidental approval', () => {
    const item: ApprovalPayload = {
      approval_id: 'appr-spend-1',
      user_id: 'u1',
      action_type: 'subagent_approval',
      status: 'PENDING',
      severity: 'info',
      payload: {
        reviewConfigs: [
          {
            isSpend: true,
            spendAmount: 25.0,
            spendCurrency: 'USD',
            actionDigest: 'digest_spend_abc',
          },
        ],
      },
    };
    const res = classifySingleApprovalRisk(item);
    expect(res.riskLevel).toBe('high');
    expect(res.reason).toContain('Financial transaction');
  });

  it('detects deep destructive shell patterns in generic bash tool payload', () => {
    const item: ApprovalPayload = {
      approval_id: 'bash-1',
      user_id: 'u1',
      action_type: 'shell_exec',
      status: 'PENDING',
      severity: 'info',
      payload: {
        tool_name: 'bash',
        command: 'rm -rf /Users/test/data',
      },
    };
    const res = classifySingleApprovalRisk(item);
    expect(res.riskLevel).toBe('high');
    expect(res.reason).toContain('Destructive command pattern detected');
  });
});
