import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SkillApprovalContent } from '../SkillApprovalContent';
import { ToolClarificationContent } from '../ToolClarificationContent';
import { BARE_DESTRUCTIVE_TEXT, makeApproval } from './approvalKit';

vi.mock('next-intl', async () => (await import('./approvalStubs')).nextIntlModule);
vi.mock(
  '@/components/features/app-shell/lazy-monaco-editor',
  async () => (await import('./approvalStubs')).monacoModule,
);

afterEach(cleanup);

describe('ToolClarificationContent', () => {
  const clarification = (reason?: string, editedArgs = '{}', onEditedArgsChange = vi.fn()) => {
    const view = render(
      <ToolClarificationContent
        approval={makeApproval('tool_clarification', undefined, { reason })}
        editedArgs={editedArgs}
        onEditedArgsChange={onEditedArgsChange}
      />,
    );
    return { ...view, onEditedArgsChange };
  };

  it('shows the error of the failed call in the destructive text colour', () => {
    const { container } = clarification('File not found: /tmp/a');

    const error = screen.getByText('File not found: /tmp/a');
    expect(screen.getByText('toolApproval.clarificationRequired')).toBeDefined();
    expect(error.className).toContain('text-destructive-text');
    expect(container.innerHTML).not.toMatch(BARE_DESTRUCTIVE_TEXT);
  });

  it('says the tool failed when the approval gives no reason', () => {
    clarification();

    expect(screen.getByText('toolApproval.toolExecutionFailed')).toBeDefined();
  });

  it('offers the arguments as a JSON editor of fixed height', () => {
    clarification('boom', '{"path":"/tmp/a"}');

    const editor = screen.getByTestId('editor') as HTMLTextAreaElement;
    expect(screen.getByText('toolApproval.fixParameters')).toBeDefined();
    expect(editor.value).toBe('{"path":"/tmp/a"}');
    expect(editor.getAttribute('data-language')).toBe('json');
    expect(editor.getAttribute('data-height')).toBe('200px');
  });

  it('reports each edit, and an emptied editor as empty text', () => {
    const { onEditedArgsChange } = clarification('boom', '{}');

    fireEvent.change(screen.getByTestId('editor'), { target: { value: '{"a":2}' } });
    fireEvent.click(screen.getByTestId('editor-clear'));

    expect(onEditedArgsChange.mock.calls).toEqual([['{"a":2}'], ['']]);
  });
});

describe('SkillApprovalContent', () => {
  const skill = (props: Partial<Parameters<typeof SkillApprovalContent>[0]> = {}) =>
    render(
      <SkillApprovalContent
        language="markdown"
        label="Skill pending"
        viewChangesLabel="View changes"
        hideChangesLabel="Hide changes"
        {...props}
      />,
    );

  it('shows the label and the reason, and no content until it is asked for', () => {
    skill({ reason: 'Learned a new routine', content: 'body' });

    expect(screen.getByText('Skill pending')).toBeDefined();
    expect(screen.getByText('Learned a new routine')).toBeDefined();
    expect(screen.queryByTestId('editor')).toBeNull();
    expect(screen.queryByTestId('diff-editor')).toBeNull();
  });

  it('leaves the reason out when there is none', () => {
    const { container } = skill({ content: 'body' });

    expect(container.querySelector('p')).toBeNull();
  });

  it('reveals the content in a read-only editor and hides it again', () => {
    skill({ content: 'new body' });

    fireEvent.click(screen.getByRole('button', { name: 'View changes' }));
    const editor = screen.getByTestId('editor') as HTMLTextAreaElement;
    expect(editor.value).toBe('new body');
    expect(editor.getAttribute('data-language')).toBe('markdown');
    expect(editor.getAttribute('data-height')).toBe('400px');
    expect(screen.queryByTestId('diff-editor')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Hide changes' }));
    expect(screen.queryByTestId('editor')).toBeNull();
    expect(screen.getByRole('button', { name: 'View changes' })).toBeDefined();
  });

  it('shows a diff against the original when there is one', () => {
    skill({ content: 'new body', originalContent: 'old body', language: 'typescript' });

    fireEvent.click(screen.getByRole('button', { name: 'View changes' }));

    const diff = screen.getByTestId('diff-editor');
    expect(diff.getAttribute('data-original')).toBe('old body');
    expect(diff.getAttribute('data-modified')).toBe('new body');
    expect(diff.getAttribute('data-language')).toBe('typescript');
    expect(screen.queryByTestId('editor')).toBeNull();
  });

  it('shows an empty editor for a draft without content', () => {
    skill();

    fireEvent.click(screen.getByRole('button', { name: 'View changes' }));

    expect((screen.getByTestId('editor') as HTMLTextAreaElement).value).toBe('');
  });
});
