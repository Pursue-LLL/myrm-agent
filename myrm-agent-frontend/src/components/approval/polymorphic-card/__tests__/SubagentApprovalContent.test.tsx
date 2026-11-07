import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApprovalToolCall } from '@/store/useApprovalStore';
import { SubagentApprovalContent } from '../SubagentApprovalContent';
import { makeApproval, shellCall, subagentApproval } from './approvalKit';
import { propsOf } from './approvalStubs';

vi.mock('next-intl', async () => (await import('./approvalStubs')).nextIntlModule);
vi.mock('../ShellToolCallApproval', async () => (await import('./approvalStubs')).shellToolCallModule);
vi.mock(
  '@/components/approval/CompactFileWriteApprovalRow',
  async () => (await import('./approvalStubs')).compactRowModule,
);
vi.mock(
  '@/components/approval/SaveSkillApprovalPreview',
  async () => (await import('./approvalStubs')).saveSkillPreviewModule,
);
vi.mock(
  '@/components/approval/ApprovalScopeNoteLine',
  async () => (await import('./approvalStubs')).scopeNoteLineModule,
);
vi.mock('@/lib/humanize', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/humanize')>()),
  humanizeApprovalTitle: (toolName: string) => `title:${toolName}`,
  resolveScopeNote: (toolName: string) => ({ text: `scope:${toolName}`, external: toolName === 'file_edit_tool' }),
}));

afterEach(cleanup);

const fileWrite = (args: Record<string, unknown>, name = 'file_write_tool'): ApprovalToolCall => ({ name, args });
const renderCalls = (calls: ApprovalToolCall[], payloadExtra: Record<string, unknown> = {}) => {
  const approval = subagentApproval(calls);
  approval.payload = { ...approval.payload, ...payloadExtra };
  return render(<SubagentApprovalContent approval={approval} />);
};
const row = () => propsOf(screen.getByTestId('CompactFileWriteApprovalRow'));

describe('SubagentApprovalContent', () => {
  it('headlines the request and shows nothing else without tool calls', () => {
    const { container } = renderCalls([]);

    expect(screen.getByText('toolApproval.subagentApprovalRequired')).toBeDefined();
    expect(container.querySelectorAll('[data-testid]')).toHaveLength(0);
  });

  it('shows nothing else when the payload names no tool calls at all', () => {
    const { container } = render(<SubagentApprovalContent approval={makeApproval('subagent_approval')} />);

    expect(screen.getByText('toolApproval.subagentApprovalRequired')).toBeDefined();
    expect(container.querySelectorAll('[data-testid], pre')).toHaveLength(0);
  });

  describe('a file write', () => {
    it('is a compact row with its title, path, content, language, labels and scope', () => {
      renderCalls([fileWrite({ path: 'src/app.ts', content: 'export {}' })]);

      expect(row()).toEqual({
        title: 'title:file_write_tool',
        filePath: 'src/app.ts',
        content: 'export {}',
        language: 'typescript',
        viewChangesLabel: 'toolApproval.viewChanges',
        hideChangesLabel: 'toolApproval.hideChanges',
        scopeNote: 'scope:file_write_tool',
        scopeExternal: false,
      });
    });

    it('marks a write that reaches outside the workspace as external', () => {
      renderCalls([fileWrite({ path: 'a.md', content: 'x' }, 'file_edit_tool')]);

      expect(row().scopeExternal).toBe(true);
    });

    it('reads the path from "path" before "file_path", ignoring one that is not text', () => {
      renderCalls([fileWrite({ path: 'one.py', file_path: 'two.rs', content: 'x' })]);
      expect(row().filePath).toBe('one.py');
      cleanup();

      renderCalls([fileWrite({ file_path: 'two.rs', content: 'x' })]);
      expect(row()).toMatchObject({ filePath: 'two.rs', language: 'rust' });
      cleanup();

      renderCalls([fileWrite({ path: 7, file_path: 'two.rs', content: 'x' })]);
      expect(row().filePath).toBe('two.rs');
      cleanup();

      renderCalls([fileWrite({ file_path: 9, content: 'x' })]);
      expect(row().filePath).toBe('');
    });

    it('reads the content from "content", "file_content" and "text" in that order', () => {
      renderCalls([fileWrite({ path: 'a.md', content: 'first', file_content: 'second', text: 'third' })]);
      expect(row().content).toBe('first');
      cleanup();

      renderCalls([fileWrite({ path: 'a.md', file_content: 'second', text: 'third' })]);
      expect(row().content).toBe('second');
      cleanup();

      renderCalls([fileWrite({ path: 'a.md', text: 'third' })]);
      expect(row().content).toBe('third');
    });

    it('is a compact row for a path without content, and for content without a path', () => {
      renderCalls([fileWrite({ path: 'empty.json' })]);
      expect(row()).toMatchObject({ filePath: 'empty.json', content: '', language: 'json' });
      cleanup();

      renderCalls([fileWrite({ content: 'only text' })]);
      expect(row()).toMatchObject({ filePath: '', content: 'only text', language: 'markdown' });
    });

    it('is shown as raw arguments when it names no path and carries no content', () => {
      renderCalls([fileWrite({ content: '   ' })]);

      expect(screen.queryByTestId('CompactFileWriteApprovalRow')).toBeNull();
      expect(screen.getByText('title:file_write_tool')).toBeDefined();
    });
  });

  describe('a shell call', () => {
    it('is handed to the shell approval with the workspace root of the payload', () => {
      const call = shellCall({ command: 'pwd' });

      renderCalls([call], { workspaceRoot: '/work/space' });

      expect(propsOf(screen.getByTestId('ShellToolCallApproval'))).toEqual({ call, workspaceRoot: '/work/space' });
    });

    it('takes the workspace root from the extensions when the payload has none of its own', () => {
      renderCalls([shellCall()], { extensions: { workspaceRoot: '/from/extensions' } });

      expect(propsOf(screen.getByTestId('ShellToolCallApproval')).workspaceRoot).toBe('/from/extensions');
    });

    it('has no workspace root when neither is text', () => {
      renderCalls([shellCall()], { workspaceRoot: 7, extensions: { workspaceRoot: false } });

      expect(propsOf(screen.getByTestId('ShellToolCallApproval')).workspaceRoot).toBeUndefined();
    });
  });

  describe('a skill save', () => {
    const saveArgs = { name: 'deploy', description: 'Ship it' };

    it.each([
      ['save_skill', saveArgs],
      ['save_skill_tool', saveArgs],
      ['skill_manage_tool', { ...saveArgs, action: 'save' }],
    ])('shows %s as a bundle preview under its title and scope note', (name, args) => {
      renderCalls([{ name, args }]);

      expect(screen.getByText(`title:${name}`)).toBeDefined();
      expect(propsOf(screen.getByTestId('ApprovalScopeNoteLine'))).toEqual({ toolName: name, toolInput: args });
      expect(propsOf(screen.getByTestId('SaveSkillApprovalPreview'))).toEqual({
        toolInput: args,
        showFullInstructionsLabel: 'toolApproval.saveSkill.showFullInstructions',
        showLessLabel: 'toolApproval.saveSkill.showLess',
        showAllLinesLabel: 'toolApproval.saveSkill.showAllLines',
        footerText: 'toolApproval.saveSkill.footer',
      });
    });

    it('is shown as raw arguments when a skill management call does not save', () => {
      renderCalls([{ name: 'skill_manage_tool', args: { ...saveArgs, action: 'delete' } }]);

      expect(screen.queryByTestId('SaveSkillApprovalPreview')).toBeNull();
      expect(screen.getByText('title:skill_manage_tool')).toBeDefined();
    });
  });

  describe('any other call', () => {
    it('shows its title, scope note and arguments as formatted JSON', () => {
      const args = { query: 'weather', limit: 3 };

      const { container } = renderCalls([{ name: 'web_search_tool', args }]);

      expect(screen.getByText('title:web_search_tool')).toBeDefined();
      expect(propsOf(screen.getByTestId('ApprovalScopeNoteLine'))).toEqual({
        toolName: 'web_search_tool',
        toolInput: args,
      });
      expect(container.querySelector('pre')?.textContent).toBe(JSON.stringify(args, null, 2));
    });

    it('shows arguments that are not an object as they are, without a scope note', () => {
      const { container } = renderCalls([
        { name: 'web_search_tool', args: 'raw text' as unknown as Record<string, unknown> },
      ]);

      expect(screen.queryByTestId('ApprovalScopeNoteLine')).toBeNull();
      expect(container.querySelector('pre')?.textContent).toBe('"raw text"');
    });
  });

  it('shows every call in its own surface, in the order of the request', () => {
    const { container } = renderCalls([
      shellCall(),
      fileWrite({ path: 'a.md', content: 'x' }),
      { name: 'save_skill', args: { name: 'n' } },
      { name: 'web_search_tool', args: { query: 'q' } },
    ]);

    const surfaces = Array.from(
      container.querySelectorAll(
        '[data-testid="ShellToolCallApproval"], [data-testid="CompactFileWriteApprovalRow"], [data-testid="SaveSkillApprovalPreview"], pre',
      ),
    ).map((node) => node.getAttribute('data-testid') ?? 'raw');
    expect(surfaces).toEqual([
      'ShellToolCallApproval',
      'CompactFileWriteApprovalRow',
      'SaveSkillApprovalPreview',
      'raw',
    ]);
  });
});
