import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApprovalPayload } from '@/store/useApprovalStore';
import { ApprovalContent } from '../ApprovalContent';
import { makeApproval } from './approvalKit';
import { propsOf } from './approvalStubs';

vi.mock('next-intl', async () => (await import('./approvalStubs')).nextIntlModule);
vi.mock('../SubagentApprovalContent', async () => (await import('./approvalStubs')).subagentContentModule);
vi.mock('../SkillApprovalContent', async () => (await import('./approvalStubs')).skillContentModule);
vi.mock('../ToolClarificationContent', async () => (await import('./approvalStubs')).toolClarificationModule);
vi.mock('../KnowledgePatchContent', async () => (await import('./approvalStubs')).knowledgePatchModule);
vi.mock('../BatchCostApprovalContent', async () => (await import('./approvalStubs')).batchCostModule);
vi.mock('../HighRiskDomActionContent', async () => (await import('./approvalStubs')).highRiskModule);
vi.mock('../McpElicitationContent', async () => (await import('./approvalStubs')).mcpElicitationModule);
vi.mock(
  '@/components/approval/OutboundDraftApprovalBody',
  async () => (await import('./approvalStubs')).outboundDraftModule,
);

afterEach(cleanup);

const renderContent = (approval: ApprovalPayload, editedArgs = '', onEditedArgsChange = vi.fn()) =>
  render(<ApprovalContent approval={approval} editedArgs={editedArgs} onEditedArgsChange={onEditedArgsChange} />);

describe('ApprovalContent', () => {
  it.each([
    ['subagent_approval', 'SubagentApprovalContent'],
    ['knowledge_patch', 'KnowledgePatchContent'],
    ['batch_cost_approval', 'BatchCostApprovalContent'],
    ['high_risk_dom_action', 'HighRiskDomActionContent'],
    ['mcp_elicitation', 'McpElicitationContent'],
  ])('lays out a %s approval with %s, handing it the whole approval', (actionType, stub) => {
    const approval = makeApproval(actionType, { content: 'c' });

    renderContent(approval);

    expect(propsOf(screen.getByTestId(stub))).toEqual({ approval });
  });

  it('lays out an outbound draft with the payload only', () => {
    const payload = { draft_content: 'Hello', channel: 'telegram' };

    renderContent(makeApproval('outbound_draft', payload));

    expect(propsOf(screen.getByTestId('OutboundDraftApprovalBody'))).toEqual({ payload });
  });

  describe('a skill draft or patch', () => {
    it.each(['skill_draft', 'skill_patch'])('shows a %s as markdown with its reason and labels', (actionType) => {
      renderContent(makeApproval(actionType, { content: 'new text', original_content: 'old text' }, { reason: 'why' }));

      expect(propsOf(screen.getByTestId('SkillApprovalContent'))).toEqual({
        reason: 'why',
        content: 'new text',
        originalContent: 'old text',
        language: 'markdown',
        label: 'toolApproval.skillGrowthPending',
        viewChangesLabel: 'toolApproval.viewChanges',
        hideChangesLabel: 'toolApproval.hideChanges',
      });
    });

    it('shows the patch text when the draft has no content', () => {
      renderContent(makeApproval('skill_patch', { patch_content: 'patched' }));

      expect(propsOf(screen.getByTestId('SkillApprovalContent')).content).toBe('patched');
    });

    it('prefers the content over the patch text', () => {
      renderContent(makeApproval('skill_patch', { content: 'content', patch_content: 'patched' }));

      expect(propsOf(screen.getByTestId('SkillApprovalContent')).content).toBe('content');
    });
  });

  describe('a tool clarification', () => {
    it('passes the editor text on and reports each change to the card', () => {
      const onEditedArgsChange = vi.fn();
      renderContent(makeApproval('tool_clarification'), '{"a":1}', onEditedArgsChange);

      expect(screen.getByTestId('ToolClarificationContent').getAttribute('data-edited-args')).toBe('{"a":1}');
      fireEvent.click(screen.getByText('edit clarification'));

      expect(onEditedArgsChange).toHaveBeenCalledExactlyOnceWith('{"fixed":true}');
    });
  });

  describe('a memory update', () => {
    const memory = (payload: ApprovalPayload['payload']) => makeApproval('semantic_memory', payload);

    it.each([
      ['the content', { content: 'remember me', patch_content: 'patch' }, 'remember me'],
      ['the patch when there is no content', { patch_content: 'patch' }, 'patch'],
      ['a placeholder when there is neither', {}, 'toolApproval.noContent'],
    ])('shows %s', (_, payload, shown) => {
      renderContent(memory(payload));

      expect(screen.getByText('toolApproval.memoryUpdate')).toBeDefined();
      expect(screen.getByText(shown)).toBeDefined();
    });
  });

  describe('any other approval', () => {
    it('shows its payload as formatted JSON under a generic heading', () => {
      const payload = { content: 'x', reason: 'y' };

      const { container } = renderContent(makeApproval('mystery_action', payload));

      expect(screen.getByText('toolApproval.payloadData')).toBeDefined();
      expect(container.querySelector('.font-mono')?.textContent).toBe(JSON.stringify(payload, null, 2));
    });
  });
});
