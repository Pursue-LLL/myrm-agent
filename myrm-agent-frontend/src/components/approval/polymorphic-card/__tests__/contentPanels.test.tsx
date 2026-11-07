import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApprovalPayloadData } from '@/store/useApprovalStore';
import { BatchCostApprovalContent } from '../BatchCostApprovalContent';
import { KnowledgePatchContent } from '../KnowledgePatchContent';
import { McpElicitationContent } from '../McpElicitationContent';
import { makeApproval } from './approvalKit';

vi.mock('next-intl', async () => (await import('./approvalStubs')).nextIntlModule);

afterEach(cleanup);

describe('KnowledgePatchContent', () => {
  const patch = (payload: ApprovalPayloadData = {}, reason?: string) =>
    render(<KnowledgePatchContent approval={makeApproval('knowledge_patch', payload, { reason })} />);

  it('names the title the payload gives, then the approval reason, then a generic title', () => {
    patch({ title: 'Payload title' }, 'Reason');
    expect(screen.getByText('Payload title')).toBeDefined();
    cleanup();

    patch({}, 'Reason');
    expect(screen.getByText('Reason')).toBeDefined();
    cleanup();

    patch();
    expect(screen.getByText('toolApproval.knowledgePatch.title')).toBeDefined();
  });

  it.each([
    [undefined, 'toolApproval.knowledgePatch.typeWiki'],
    ['wiki', 'toolApproval.knowledgePatch.typeWiki'],
    ['procedural', 'toolApproval.knowledgePatch.typeProcedural'],
    ['skill_gap', 'toolApproval.knowledgePatch.typeSkillGap'],
    ['anything-else', 'toolApproval.knowledgePatch.typeSkillGap'],
  ])('labels a "%s" target as %s', (target_type, label) => {
    patch({ target_type });

    expect(screen.getByText(label)).toBeDefined();
  });

  it.each([
    [undefined, '80%'],
    ['0.9' as unknown as number, '80%'],
    [0, '0%'],
    [0.456, '46%'],
    [1, '100%'],
  ])('shows a confidence of %s as %s', (confidence, shown) => {
    patch({ confidence });

    expect(screen.getByText(shown)).toBeDefined();
  });

  it('shows the content, or a placeholder without one', () => {
    patch({ content: 'Always run the linter' });
    expect(screen.getByText('Always run the linter')).toBeDefined();
    cleanup();

    patch();
    expect(screen.getByText('toolApproval.noContent')).toBeDefined();
  });

  it('shows the trigger, rationale and source queries only when the payload has them', () => {
    patch();
    expect(screen.queryByText('toolApproval.knowledgePatch.triggerCondition')).toBeNull();
    expect(screen.queryByText('toolApproval.knowledgePatch.rationale')).toBeNull();
    expect(screen.queryByText('toolApproval.knowledgePatch.sourceQueries')).toBeNull();
    cleanup();

    patch({
      trigger_condition: 'when CI fails',
      rationale: 'it keeps failing',
      source_queries: ['how to fix ci', 'ci timeout'],
    });

    expect(screen.getByText('when CI fails')).toBeDefined();
    expect(screen.getByText('it keeps failing')).toBeDefined();
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['how to fix ci', 'ci timeout']);
  });

  it('ignores source queries that are not a list', () => {
    patch({ source_queries: 'oops' as unknown as string[] });

    expect(screen.queryByText('toolApproval.knowledgePatch.sourceQueries')).toBeNull();
  });
});

describe('BatchCostApprovalContent', () => {
  const batch = (payload: ApprovalPayloadData = {}) =>
    render(<BatchCostApprovalContent approval={makeApproval('batch_cost_approval', payload)} />);

  it('says what is being approved', () => {
    batch();

    expect(screen.getByText('toolApproval.batchCostTitle')).toBeDefined();
    expect(screen.getByText('toolApproval.batchCostDescription')).toBeDefined();
  });

  it('shows the estimated cost in dollars with two decimals and the number of subagents', () => {
    batch({ estimated_cost_usd: 1.5, task_count: 4 });

    expect(screen.getByText('$1.50')).toBeDefined();
    expect(screen.getByText('4')).toBeDefined();
  });

  it('shows zero for a cost and a count that are missing', () => {
    batch();

    expect(screen.getByText('$0.00')).toBeDefined();
    expect(screen.getByText('0')).toBeDefined();
  });

  it('shows the remaining budget only when it is known, zero included', () => {
    batch();
    expect(screen.queryByText('toolApproval.batchCostRemaining')).toBeNull();
    cleanup();

    batch({ remaining_budget_usd: 0 });
    expect(screen.getByText('toolApproval.batchCostRemaining')).toBeDefined();
    expect(screen.getByText('$0.00', { selector: '.font-mono' })).toBeDefined();
  });

  it.each([
    [{}, 'toolApproval.batchCostParallel'],
    [{ race: true }, 'toolApproval.batchCostRace'],
    [{ tournament: true }, 'toolApproval.batchCostTournament'],
    [{ race: true, tournament: true }, 'toolApproval.batchCostTournament'],
  ])('labels the run mode of %j as %s', (flags, label) => {
    batch(flags);

    expect(screen.getByText(label)).toBeDefined();
  });

  it('shows the cost status unless it is empty or unknown', () => {
    const statusPill = () => document.querySelector('.rounded-full');

    batch({ cost_status: 'estimated' });
    expect(statusPill()?.textContent).toBe('estimated');
    cleanup();

    batch({ cost_status: 'unknown' });
    expect(statusPill()).toBeNull();
    cleanup();

    batch();
    expect(statusPill()).toBeNull();
  });

  it('shows no task list without tasks', () => {
    batch();

    expect(document.querySelector('.overflow-y-auto')).toBeNull();
  });

  it('lists each task with its agent type and objective', () => {
    batch({
      tasks: [
        { agent_type: 'researcher', objective: 'Find the sources' },
        { agent_type: 'writer', objective: 'Draft the summary' },
      ],
    });

    expect(screen.getByText('researcher')).toBeDefined();
    expect(screen.getByText('Find the sources')).toBeDefined();
    expect(screen.getByText('writer')).toBeDefined();
    expect(screen.getByText('Draft the summary')).toBeDefined();
  });
});

describe('McpElicitationContent', () => {
  const elicitation = (payload: ApprovalPayloadData = {}, reason?: string) =>
    render(<McpElicitationContent approval={makeApproval('mcp_elicitation', payload, { reason })} />);

  it('names the server that asks, only when the payload names one', () => {
    elicitation({ server_name: 'github' });
    expect(screen.getByText('github')).toBeDefined();
    cleanup();

    elicitation();
    expect(screen.queryByText('toolApproval.mcpElicitationServer', { exact: false })).toBeNull();
  });

  it('shows the message of the server, or the approval reason without one', () => {
    elicitation({ message: 'Which repo?' }, 'fallback reason');
    expect(screen.getByText('Which repo?')).toBeDefined();
    expect(screen.queryByText('fallback reason')).toBeNull();
    cleanup();

    elicitation({}, 'fallback reason');
    expect(screen.getByText('fallback reason')).toBeDefined();
  });

  it('lists the requested fields with their type and description', () => {
    elicitation({
      requested_schema: {
        properties: {
          repo: { type: 'string', description: 'owner/name' },
          limit: { type: 'number' },
          note: { description: 'free text' },
          bare: {},
        },
      },
    });

    const rows = Array.from(document.querySelectorAll('.text-xs.font-mono')).map((row) => row.textContent);
    expect(rows).toEqual(['repo (string): owner/name', 'limit (number)', 'note: free text', 'bare']);
  });

  it.each([
    ['a schema without properties', { requested_schema: { type: 'object' } }],
    ['no schema', {}],
  ])('shows no field list for %s', (_, payload) => {
    elicitation(payload);

    expect(document.querySelector('.bg-muted')).toBeNull();
  });
});
