import { describe, expect, it } from 'vitest';

import type { ProgressItem } from '@/store/chat/types';
import { getStepTitle, isDelegationToolLine } from '../utils';

const t = (key: string, values?: { agentName?: string }) => (values?.agentName ? `${key}|${values.agentName}` : key);

const delegationStep = (stepKey: string, overrides: Partial<ProgressItem> = {}): ProgressItem => ({
  step_key: stepKey,
  tool_name: 'delegate:claude',
  status: 'complete',
  ...overrides,
});

const toolLine = { items: [{ text: 'claude: Read — note.txt' }] };

describe('getStepTitle delegation steps', () => {
  it('words the delegation status line with the agent name', () => {
    expect(getStepTitle(delegationStep('delegation_claude_status'), t)).toBe('delegation|claude');
  });

  it.each([
    ['delegation_claude_session_expired', 'delegation_session_expired|claude'],
    ['delegation_claude_session_workspace_changed', 'delegation_session_workspace_changed|claude'],
  ])('words the continuity notice %s from its step key alone', (stepKey, title) => {
    expect(getStepTitle(delegationStep(stepKey, { items: [] }), t)).toBe(title);
  });

  it('keeps agent names that contain underscores intact', () => {
    expect(getStepTitle(delegationStep('delegation_code_review_status'), t)).toBe('delegation|code_review');
    expect(getStepTitle(delegationStep('delegation_code_review_tool', toolLine), t)).toBe('claude: Read — note.txt');
    expect(getStepTitle(delegationStep('delegation_my_status_session_expired'), t)).toBe(
      'delegation_session_expired|my_status',
    );
  });

  it('titles a delegated tool call with its own line instead of the generic delegate tool name', () => {
    expect(getStepTitle(delegationStep('delegation_claude_tool', toolLine), t)).toBe('claude: Read — note.txt');
  });

  it('falls back to the generic title for a tool step without a text line', () => {
    const title = getStepTitle(delegationStep('delegation_claude_tool'), t);
    expect(title).not.toBe('claude: Read — note.txt');
    expect(title).not.toBe('');
  });

  it('leaves other step keys alone', () => {
    expect(getStepTitle({ step_key: 'delegation_overview', status: 'complete' }, t)).not.toContain('delegation|');
  });
});

describe('isDelegationToolLine', () => {
  it('is true only for a delegated tool step that carries its text line', () => {
    expect(isDelegationToolLine(delegationStep('delegation_claude_tool', toolLine))).toBe(true);
    expect(isDelegationToolLine(delegationStep('delegation_code_review_tool', toolLine))).toBe(true);
    expect(isDelegationToolLine(delegationStep('delegation_claude_tool'))).toBe(false);
    expect(isDelegationToolLine(delegationStep('delegation_claude_tool', { items: [] }))).toBe(false);
    expect(isDelegationToolLine(delegationStep('delegation_claude_status', toolLine))).toBe(false);
    expect(isDelegationToolLine({ step_key: 'bash_tool', ...toolLine })).toBe(false);
  });
});
