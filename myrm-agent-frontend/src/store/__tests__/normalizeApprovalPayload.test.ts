import { describe, expect, it } from 'vitest';

import { normalizeApprovalPayload } from '@/store/useApprovalStore';

describe('normalizeApprovalPayload', () => {
  it('preserves flat semantic DOM HITL fields from SSE interrupt payload', () => {
    const expression = "document.querySelector('.pay').click()";
    const normalized = normalizeApprovalPayload({
      approval_id: 'appr-1',
      user_id: 'user-1',
      action_type: 'high_risk_dom_action',
      status: 'PENDING',
      severity: 'critical',
      reason: 'Mutating JS evaluate',
      chat_id: 'chat-1',
      tool_name: 'browser_manage_tool',
      tool_input: { action: 'evaluate', expression },
      page_url: 'https://shop.example.com/checkout',
    });

    expect(normalized.action_type).toBe('high_risk_dom_action');
    expect(normalized.payload?.tool_input).toEqual({ action: 'evaluate', expression });
    expect(normalized.payload?.page_url).toBe('https://shop.example.com/checkout');
    expect(normalized.payload?.tool_name).toBe('browser_manage_tool');
  });

  it('preserves click element metadata from nested payload', () => {
    const normalized = normalizeApprovalPayload({
      approval_id: 'appr-2',
      user_id: 'user-1',
      action_type: 'high_risk_dom_action',
      status: 'PENDING',
      severity: 'critical',
      payload: {
        tool_input: { action: 'click', ref: 'e5', text: '' },
        element: { role: 'button', name: 'Delete Repository', ref: 'e5' },
        page_url: 'https://github.com/settings',
      },
    });

    expect(normalized.payload?.element).toEqual({
      role: 'button',
      name: 'Delete Repository',
      ref: 'e5',
    });
    expect(normalized.payload?.tool_input).toEqual({ action: 'click', ref: 'e5', text: '' });
  });

  it('preserves flat element fields from SSE interrupt at top level', () => {
    const normalized = normalizeApprovalPayload({
      approval_id: 'appr-3',
      user_id: 'user-1',
      action_type: 'high_risk_dom_action',
      status: 'PENDING',
      severity: 'critical',
      tool_name: 'browser_interact_tool',
      tool_input: { action: 'click', ref: 'e5', text: '' },
      element: { role: 'button', name: 'Pay Now', ref: 'e5' },
      page_url: 'https://shop.example.com/pay',
    });

    expect(normalized.payload?.element).toEqual({ role: 'button', name: 'Pay Now', ref: 'e5' });
    expect(normalized.payload?.page_url).toBe('https://shop.example.com/pay');
  });

  it('normalizes GET /approvals API record shape for drawer recovery', () => {
    const normalized = normalizeApprovalPayload({
      id: 'recovered-1',
      action_type: 'high_risk_dom_action',
      status: 'PENDING',
      severity: 'warning',
      reason: 'Mutating JS evaluate',
      chat_id: 'chat-recover',
      payload: {
        tool_name: 'browser_manage_tool',
        tool_input: { action: 'evaluate', expression: 'document.forms[0].submit()' },
        page_url: 'https://example.com/form',
      },
    });

    expect(normalized.approval_id).toBe('recovered-1');
    expect(normalized.payload?.tool_input?.expression).toBe('document.forms[0].submit()');
    expect(normalized.payload?.page_url).toBe('https://example.com/form');
  });
});
