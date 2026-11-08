import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ProgressItem } from '@/store/chat/types';
import { ProgressStepNode, StepNodes, type StepNodeContext } from '../ProgressStepNode';
import type { TreeNode } from '../treeUtils';
import { BARE_DESTRUCTIVE_TEXT, makeContext, makeNode, makeStep } from './progressStepsKit';

vi.mock('../StepOutput', async () => (await import('./progressStepsStubs')).outputModule);
vi.mock('../ArchiveRestoreStepAction', async () => (await import('./progressStepsStubs')).archiveActionModule);
vi.mock('../ArchiveRestoreResultChip', async () => (await import('./progressStepsStubs')).archiveResultModule);
vi.mock('../SkillManageBatchRollbackAction', async () => (await import('./progressStepsStubs')).rollbackModule);

const ERROR = 'The upstream service refused the call.';

function renderNode(node: TreeNode, options: { depth?: number; ctx?: StepNodeContext } = {}) {
  const { depth = 0, ctx = makeContext() } = options;
  return render(<ProgressStepNode node={node} depth={depth} ctx={ctx} />);
}

/** A plan step with a reason, an error and output, to tell its body from its header. */
const planWithBody = (): ProgressItem =>
  makeStep({
    step_key: 'plan',
    is_plan: true,
    reason: 'Because the plan says so',
    status: 'error',
    error: ERROR,
    stdout: 'plan output',
  });

describe('ProgressStepNode body', () => {
  it('draws the header, reason, error and output of a step', () => {
    renderNode(makeNode(makeStep({ reason: 'Because it was asked', status: 'error', error: ERROR })));

    expect(screen.getByRole('heading', { level: 4 })).toHaveTextContent('Alpha');
    expect(screen.getByText('Because it was asked')).toBeInTheDocument();
    expect(screen.getByText(ERROR)).toHaveClass('text-destructive-text');
    expect(screen.getByTestId('items-view')).toBeInTheDocument();
    expect(screen.getByTestId('terminal')).toHaveAttribute('data-step-key', 'alpha');
  });

  it('draws no reason, error or archive entries for a step that has none', () => {
    const { container } = renderNode(makeNode(makeStep()));

    expect(container.querySelector('p')).toBeNull();
    expect(screen.queryByText(ERROR)).not.toBeInTheDocument();
    expect(screen.queryByTestId('archive-restore-action')).not.toBeInTheDocument();
    expect(screen.queryByTestId('archive-restore-result')).not.toBeInTheDocument();
    expect(screen.queryByTestId('skill-rollback')).not.toBeInTheDocument();
  });

  it('hands the items its step, its message and its position in the message', () => {
    renderNode(makeNode(makeStep({ step_key: 'beta' }), 4), { ctx: makeContext({ messageId: 'msg-9', lastIndex: 7 }) });

    const items = screen.getByTestId('items-view');
    expect(items).toHaveAttribute('data-step-key', 'beta');
    expect(items).toHaveAttribute('data-message-id', 'msg-9');
    expect(items).toHaveAttribute('data-index', '4');
  });

  it('draws no error text in the fill token', () => {
    const { container } = renderNode(makeNode(makeStep({ status: 'error', error: ERROR, error_hint: 'Try later.' })));

    expect(container.innerHTML).not.toMatch(BARE_DESTRUCTIVE_TEXT);
  });
});

describe('ProgressStepNode in flight', () => {
  it.each([
    ['the newest step while loading', 2, 2, true, 'true'],
    ['the newest step once loading is over', 2, 2, false, 'false'],
    ['an older step while loading', 1, 2, true, 'false'],
  ])('knows %s is in flight: %s', (_name, index, lastIndex, loading, current) => {
    const { container } = renderNode(makeNode(makeStep({ status: undefined }), index), {
      ctx: makeContext({ lastIndex, loading }),
    });

    expect(screen.getByTestId('items-view')).toHaveAttribute('data-current', current);
    expect(container.querySelectorAll('.animate-rotate-step').length > 0).toBe(current === 'true');
  });
});

describe('ProgressStepNode plans and children', () => {
  const child = (key: string, index: number, children: TreeNode[] = []) =>
    makeNode(makeStep({ step_key: key }), index, children);

  it('draws only the header and the children of a plan that has children', () => {
    renderNode(makeNode(planWithBody(), 0, [child('child_one', 1)]));

    expect(screen.getByRole('heading', { name: 'Plan' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Child One' })).toBeInTheDocument();
    expect(screen.queryByText('Because the plan says so')).not.toBeInTheDocument();
    expect(screen.queryByText(ERROR)).not.toBeInTheDocument();
    expect(screen.getAllByTestId('items-view')).toHaveLength(1);
    expect(screen.getAllByTestId('terminal')).toHaveLength(1);
  });

  it('draws the whole body of a plan that has no children', () => {
    renderNode(makeNode(planWithBody()));

    expect(screen.getByText('Because the plan says so')).toBeInTheDocument();
    expect(screen.getByText(ERROR)).toBeInTheDocument();
    expect(screen.getByTestId('terminal')).toBeInTheDocument();
  });

  it('draws the body of a step that is not a plan together with its children', () => {
    renderNode(makeNode(makeStep({ reason: 'Own reason' }), 0, [child('child_one', 1)]));

    expect(screen.getByText('Own reason')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Child One' })).toBeInTheDocument();
  });

  it('nests the children, each level indented further than the root, and draws a rail only where there are children', () => {
    const { container } = renderNode(
      makeNode(makeStep({ step_key: 'root' }), 0, [child('mid', 1, [child('leaf', 2)])]),
    );

    const nodeOf = (title: string) => screen.getByRole('heading', { name: title }).closest('.group') as HTMLElement;
    expect(nodeOf('Root')).toHaveClass('-ml-1', 'pl-1');
    expect(nodeOf('Mid')).toHaveClass('ml-4', 'mt-2');
    expect(nodeOf('Leaf')).toHaveClass('ml-4', 'mt-2');
    expect(container.querySelectorAll('.bg-gradient-to-b')).toHaveLength(2);
  });

  it('draws no rail for a step without children', () => {
    const { container } = renderNode(makeNode(makeStep()));

    expect(container.querySelector('.bg-gradient-to-b')).toBeNull();
  });

  it('draws the children in order, and tells steps of the same key apart without a key warning', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    renderNode(makeNode(makeStep({ step_key: 'root' }), 0, [child('same', 1), child('same', 2), child('other', 3)]));

    expect(screen.getAllByRole('heading', { level: 4 }).map((heading) => heading.textContent)).toEqual([
      'Root',
      'Same',
      'Same',
      'Other',
    ]);
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});

describe('ProgressStepNode extras', () => {
  it('opens the detail of the step through the context', () => {
    const step = makeStep({ step_key: 'beta' });
    const onViewDetail = vi.fn();
    renderNode(makeNode(step), { ctx: makeContext({ onViewDetail }) });

    fireEvent.click(screen.getByTitle('viewDetailTooltip'));

    expect(onViewDetail).toHaveBeenCalledExactlyOnceWith(step);
  });

  it('draws the restore entry for archive restore actions, and none for an empty list', () => {
    const action = { type: 'archive_restore' as const, restoreArg: 'archive.txt:1-5' };
    const { unmount } = renderNode(makeNode(makeStep({ archive_restore_actions: [action, action] })));
    expect(screen.getByTestId('archive-restore-action')).toHaveAttribute('data-count', '2');
    unmount();

    renderNode(makeNode(makeStep({ archive_restore_actions: [] })));
    expect(screen.queryByTestId('archive-restore-action')).not.toBeInTheDocument();
  });

  it('draws the restore result of a step that carries one', () => {
    renderNode(
      makeNode(
        makeStep({
          archive_restore_result: {
            type: 'archive_restore_result',
            outcome: 'restored',
            archive_path: 'archive.txt',
            restore_arg: 'archive.txt:1-5',
            start_line: 1,
            end_line: 5,
            restored_line_count: 5,
            estimated_tokens: 10,
            restored_bytes: 40,
          },
        }),
      ),
    );

    expect(screen.getByTestId('archive-restore-result')).toHaveAttribute('data-restore-arg', 'archive.txt:1-5');
  });

  it('offers the undo of a skill save by its batch', () => {
    renderNode(makeNode(makeStep({ tool_name: 'skill_manage_tool', skill_mutation_batch_id: 'batch-7' })));

    expect(screen.getByTestId('skill-rollback')).toHaveAttribute('data-batch-id', 'batch-7');
  });

  it('offers no undo for a skill save that failed', () => {
    renderNode(
      makeNode(
        makeStep({ tool_name: 'skill_manage_tool', skill_mutation_batch_id: 'batch-7', status: 'error', error: ERROR }),
      ),
    );

    expect(screen.queryByTestId('skill-rollback')).not.toBeInTheDocument();
  });
});

describe('ProgressStepNode dropped constraints', () => {
  const manifest = (count: number) => Array.from({ length: count }, (_, index) => `constraint ${index + 1}`);

  it('draws no list without dropped constraints', () => {
    renderNode(makeNode(makeStep({ dropped_manifest: [] })));

    expect(screen.queryByText('dropped_manifest_title')).not.toBeInTheDocument();
  });

  it('lists up to three constraints in full', () => {
    renderNode(makeNode(makeStep({ dropped_manifest: manifest(3) })));

    expect(screen.getByText('dropped_manifest_title')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'constraint 1',
      'constraint 2',
      'constraint 3',
    ]);
    expect(screen.queryByText(/^dropped_manifest_more/)).not.toBeInTheDocument();
  });

  it('lists the first three and counts the rest', () => {
    renderNode(makeNode(makeStep({ dropped_manifest: manifest(5) })));

    expect(screen.getAllByRole('listitem')).toHaveLength(3);
    expect(screen.getByText('dropped_manifest_more:{"count":2}')).toBeInTheDocument();
  });
});

describe('StepNodes', () => {
  it('draws one node for each entry, in order, at the depth it was given', () => {
    render(
      <StepNodes
        nodes={[makeNode(makeStep({ step_key: 'first' }), 0), makeNode(makeStep({ step_key: 'second' }), 1)]}
        depth={1}
        ctx={makeContext()}
      />,
    );

    const titles = screen.getAllByRole('heading', { level: 4 });
    expect(titles.map((title) => title.textContent)).toEqual(['First', 'Second']);
    expect(titles[0].closest('.group')).toHaveClass('ml-4', 'mt-2');
  });
});
