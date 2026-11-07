import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { scopeToAllowAlwaysValue } from '@/lib/approval/allowAlwaysScope';
import type { ApprovalToolCall } from '@/store/useApprovalStore';
import { useShellEdit } from '../useShellEdit';
import { shellCall } from './approvalKit';

const mocks = vi.hoisted(() => ({ toast: { error: vi.fn() } }));

vi.mock('next-intl', async () => (await import('./approvalStubs')).nextIntlModule);
vi.mock('sonner', () => ({ toast: mocks.toast }));

const SHELL_TOOL = 'bash_code_execute_tool';

interface HookProps {
  approvalId: string;
  toolCalls: ApprovalToolCall[];
  isSubagentApproval: boolean;
  primaryToolName: string;
  comment: string;
}

const setup = (overrides: Partial<HookProps> = {}) => {
  const onResolve = vi.fn().mockResolvedValue(undefined);
  const initialProps: HookProps = {
    approvalId: 'a1',
    toolCalls: [shellCall()],
    isSubagentApproval: true,
    primaryToolName: SHELL_TOOL,
    comment: '',
    ...overrides,
  };
  const hook = renderHook((props: HookProps) => useShellEdit({ ...props, onResolve }), { initialProps });
  const confirm = () =>
    act(async () => {
      await hook.result.current.editView.onConfirm();
    });
  const setArgs = (args: Record<string, string>) =>
    act(() => {
      hook.result.current.editView.setEditedArgs(args);
    });
  return { ...hook, onResolve, confirm, setArgs, initialProps };
};

describe('useShellEdit', () => {
  beforeEach(() => {
    mocks.toast.error.mockClear();
  });

  describe('which call can be edited', () => {
    it.each([
      ['an approval that is not a subagent approval', { isSubagentApproval: false }],
      ['two tool calls', { toolCalls: [shellCall(), shellCall({ command: 'pwd' })] }],
      ['no tool call', { toolCalls: [] }],
      ['a tool that is not a shell tool', { toolCalls: [{ name: 'web_search_tool', args: { command: 'x' } }] }],
      [
        'a call without arguments',
        { toolCalls: [{ name: SHELL_TOOL, args: null as unknown as Record<string, unknown> }] },
      ],
      [
        'a call whose arguments are text',
        { toolCalls: [{ name: SHELL_TOOL, args: 'ls' as unknown as Record<string, unknown> }] },
      ],
    ])('has nothing to edit for %s', (_, overrides) => {
      const { result } = setup(overrides);

      expect(result.current.singleShellToolCall).toBeNull();
      expect(result.current.shellCommand).toBe('');
      expect(result.current.editView.inputEntries).toEqual([]);
    });

    it('exposes the single shell call, its command and its editable arguments without the span metadata', () => {
      const call = shellCall({
        command: 'ls -la',
        timeout: 30,
        command_spans: [{ startIndex: 0, endIndex: 2 }],
        plain_explanation: { en: 'list', zh: '列出' },
      });
      const { result } = setup({ toolCalls: [call] });

      expect(result.current.singleShellToolCall).toBe(call);
      expect(result.current.shellCommand).toBe('ls -la');
      expect(result.current.editView.inputEntries).toEqual([
        ['command', 'ls -la'],
        ['timeout', 30],
      ]);
      expect(result.current.editView.isSingleStringParam).toBe(false);
    });

    it('knows when the command is the only editable argument and a string', () => {
      expect(setup().result.current.editView.isSingleStringParam).toBe(true);
      expect(setup({ toolCalls: [shellCall({ timeout: 30 })] }).result.current.editView.isSingleStringParam).toBe(
        false,
      );
    });
  });

  describe('the edit fields', () => {
    it('start from the arguments: strings as they are, nothing as empty, anything else as formatted JSON', () => {
      const { result } = setup({
        toolCalls: [shellCall({ command: 'ls', env: { A: 1 }, cwd: null, note: undefined, timeout: 30 })],
      });

      expect(result.current.editView.editedArgs).toEqual({
        command: 'ls',
        env: '{\n  "A": 1\n}',
        cwd: '',
        note: '',
        timeout: '30',
      });
    });

    it('start over when the call changes', () => {
      const { result, rerender, initialProps } = setup();

      rerender({ ...initialProps, toolCalls: [shellCall({ command: 'pwd' })] });

      expect(result.current.editView.editedArgs).toEqual({ command: 'pwd' });
    });

    it('report the edited command, apart from the command the call was made with', () => {
      const { result, setArgs } = setup();
      expect(result.current.editView.shellCommand).toBe('ls -la');

      setArgs({ command: 'echo hi' });

      expect(result.current.editView.shellCommand).toBe('echo hi');
      expect(result.current.shellCommand).toBe('ls -la');
    });
  });

  describe('an edit session', () => {
    it('opens and closes, and keeps what was typed when it is cancelled', () => {
      const { result, setArgs } = setup();
      expect(result.current.isEditing).toBe(false);

      act(() => result.current.startEditing());
      expect(result.current.isEditing).toBe(true);
      setArgs({ command: 'ls -l' });
      act(() => result.current.editView.onCancel());

      expect(result.current.isEditing).toBe(false);
      expect(result.current.editView.editedArgs).toEqual({ command: 'ls -l' });
    });

    it('clears the allow-always choice and the validation errors when it is cancelled', async () => {
      const { result, setArgs, confirm } = setup();
      act(() => result.current.startEditing());
      act(() => result.current.editView.setAllowAlwaysInEdit(true));
      setArgs({ command: '{"broken":' });
      await confirm();
      expect(result.current.editView.editValidationErrors).toEqual(['command']);

      act(() => result.current.editView.onCancel());

      expect(result.current.editView.allowAlwaysInEdit).toBe(false);
      expect(result.current.editView.editValidationErrors).toEqual([]);
    });
  });

  describe('confirming without changes', () => {
    it('approves the call as it is, with the comment as guidance', async () => {
      const { onResolve, confirm, rerender, initialProps } = setup();
      await confirm();
      expect(onResolve).toHaveBeenLastCalledWith('approve', '', undefined, {
        allow_always: undefined,
        ttl_seconds: undefined,
        guidance: undefined,
      });

      rerender({ ...initialProps, comment: 'looks fine' });
      await confirm();
      expect(onResolve).toHaveBeenLastCalledWith('approve', 'looks fine', undefined, {
        allow_always: undefined,
        ttl_seconds: undefined,
        guidance: 'looks fine',
      });
    });

    it('does not count an object argument the user left alone as a change', async () => {
      const { onResolve, confirm } = setup({ toolCalls: [shellCall({ command: 'ls', env: { A: 1 }, paths: ['/'] })] });

      await confirm();

      expect(onResolve.mock.calls[0][0]).toBe('approve');
    });

    it('also grants a standing allowance of the chosen scope and duration', async () => {
      const { result, onResolve, confirm } = setup();
      act(() => result.current.editView.setAllowAlwaysInEdit(true));
      await confirm();
      expect(onResolve).toHaveBeenLastCalledWith('approve', '', undefined, {
        allow_always: scopeToAllowAlwaysValue('exact', 'session'),
        ttl_seconds: -1,
        guidance: undefined,
      });

      act(() => {
        result.current.editView.setAllowAlwaysInEdit(true);
        result.current.editView.setAllowAlwaysScopeInEdit('tool');
        result.current.editView.setAllowAlwaysDurationInEdit('1h');
      });
      await confirm();
      expect(onResolve).toHaveBeenLastCalledWith('approve', '', undefined, {
        allow_always: scopeToAllowAlwaysValue('tool', '1h'),
        ttl_seconds: 3600,
        guidance: undefined,
      });
    });

    it('leaves the edit session and returns the allow-always choice to its defaults', async () => {
      const { result, confirm } = setup();
      act(() => result.current.startEditing());
      act(() => {
        result.current.editView.setAllowAlwaysInEdit(true);
        result.current.editView.setAllowAlwaysScopeInEdit('pattern');
        result.current.editView.setAllowAlwaysDurationInEdit('1h');
      });

      await confirm();

      expect(result.current.isEditing).toBe(false);
      expect(result.current.editView.allowAlwaysInEdit).toBe(false);
      expect(result.current.editView.allowAlwaysScopeInEdit).toBe('exact');
      expect(result.current.editView.allowAlwaysDurationInEdit).toBe('session');
    });
  });

  describe('confirming with changes', () => {
    const original = shellCall({
      command: 'ls -la',
      timeout: 30,
      run_in_background: true,
      command_spans: [{ startIndex: 0, endIndex: 2 }],
    });

    it('sends the edited arguments merged onto the original ones, minus the span metadata', async () => {
      const { onResolve, confirm, setArgs } = setup({ toolCalls: [original], comment: 'safer' });

      setArgs({ command: 'ls -l', timeout: '45', run_in_background: 'true' });
      await confirm();

      expect(onResolve).toHaveBeenCalledExactlyOnceWith('edit', 'safer', undefined, {
        edited_args: { command: 'ls -l', timeout: 45, run_in_background: true },
        allow_always: false,
        ttl_seconds: undefined,
        guidance: 'safer',
      });
    });

    it('keeps an edited field that is not JSON as text, and sends no guidance without a comment', async () => {
      const { onResolve, confirm, setArgs } = setup({ toolCalls: [original] });

      setArgs({ command: 'echo {hi}', timeout: '30', run_in_background: 'true' });
      await confirm();

      expect(onResolve).toHaveBeenCalledExactlyOnceWith('edit', '', undefined, {
        edited_args: { command: 'echo {hi}', timeout: 30, run_in_background: true },
        allow_always: false,
        ttl_seconds: undefined,
        guidance: undefined,
      });
    });

    it('keeps the original arguments that are not offered for editing', async () => {
      const args = { command: 'ls', opt1: 1, opt2: 2, opt3: 3, opt4: 4, opt5: 5, opt6: 6, opt7: 7, opt8: 8 };
      const { result, onResolve, confirm, setArgs } = setup({ toolCalls: [shellCall(args)] });
      expect(result.current.editView.inputEntries).toHaveLength(8);

      setArgs({ ...result.current.editView.editedArgs, command: 'ls -l' });
      await confirm();

      expect(onResolve.mock.calls[0][3].edited_args).toEqual({ ...args, command: 'ls -l' });
    });

    it('adds the standing allowance the user asked for, and leaves the edit session', async () => {
      const { result, onResolve, confirm, setArgs } = setup({ toolCalls: [original] });
      act(() => result.current.startEditing());
      act(() => {
        result.current.editView.setAllowAlwaysInEdit(true);
        result.current.editView.setAllowAlwaysDurationInEdit('15m');
      });

      setArgs({ command: 'ls -l', timeout: '30', run_in_background: 'true' });
      await confirm();

      expect(onResolve.mock.calls[0][3]).toMatchObject({
        allow_always: scopeToAllowAlwaysValue('exact', '15m'),
        ttl_seconds: 900,
      });
      expect(result.current.isEditing).toBe(false);
    });
  });

  describe('validating the edits', () => {
    it('refuses a field that looks like JSON but is not, names it, and stays in the edit session', async () => {
      const { result, onResolve, confirm, setArgs } = setup();
      act(() => result.current.startEditing());

      setArgs({ command: '{"broken":' });
      await confirm();

      expect(onResolve).not.toHaveBeenCalled();
      expect(result.current.editView.editValidationErrors).toEqual(['command']);
      expect(mocks.toast.error).toHaveBeenCalledExactlyOnceWith(
        'toolApproval.editValidationError:{"fields":"command"}',
      );
      expect(result.current.isEditing).toBe(true);
    });

    it('names every such field, also when the JSON-like text follows blanks', async () => {
      const { onResolve, confirm, setArgs } = setup({ toolCalls: [shellCall({ command: 'ls', cwd: '/' })] });

      setArgs({ command: '[1,', cwd: '  {oops' });
      await confirm();

      expect(onResolve).not.toHaveBeenCalled();
      expect(mocks.toast.error).toHaveBeenCalledExactlyOnceWith(
        'toolApproval.editValidationError:{"fields":"command, cwd"}',
      );
    });

    it('clears the errors once the edits are valid again', async () => {
      const { result, onResolve, confirm, setArgs } = setup();
      setArgs({ command: '{"broken":' });
      await confirm();
      expect(result.current.editView.editValidationErrors).toEqual(['command']);

      setArgs({ command: 'ls -l' });
      await confirm();

      expect(result.current.editView.editValidationErrors).toEqual([]);
      expect(onResolve).toHaveBeenCalledTimes(1);
    });
  });
});
