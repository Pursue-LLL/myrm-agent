import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PolymorphicApprovalCard } from '@/components/approval/PolymorphicApprovalCard';
import { scopeToAllowAlwaysValue } from '@/lib/approval/allowAlwaysScope';
import type { ApprovalPayload, ApprovalPayloadData } from '@/store/useApprovalStore';
import { makeApproval, shellCall, subagentApproval } from './approvalKit';

vi.mock('next-intl', async () => (await import('./approvalStubs')).nextIntlModule);
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('sonner', () => ({ toast: { custom: vi.fn(), dismiss: vi.fn(), error: vi.fn() } }));
vi.mock('@/store/useApprovalStore', () => ({
  default: (select: (state: { hideDrawer: () => void }) => unknown) => select({ hideDrawer: vi.fn() }),
}));
vi.mock(
  '@/components/features/app-shell/lazy-monaco-editor',
  async () => (await import('./approvalStubs')).monacoModule,
);
vi.mock(
  '@/components/features/chat-window/approval/EditModeView',
  async () => (await import('./approvalStubs')).editModeViewModule,
);
vi.mock(
  '@/components/features/chat-window/approval/AllowAlwaysConfirmDialog',
  async () => (await import('./approvalStubs')).allowAlwaysDialogModule,
);

afterEach(cleanup);

const T = {
  reject: 'toolApproval.reject',
  approve: 'toolApproval.approve',
  edit: 'toolApproval.edit',
  allowAlways: 'toolApproval.allowAlways',
  comment: 'toolApproval.commentsOptional',
};

const renderCard = (approval: ApprovalPayload, isSubmitting = false) => {
  const onResolve = vi.fn().mockResolvedValue(undefined);
  const view = render(
    <PolymorphicApprovalCard approval={approval} onResolve={onResolve} isSubmitting={isSubmitting} />,
  );
  return { ...view, onResolve };
};

const click = async (name: string | RegExp) => {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name }));
  });
};
const queryButton = (name: string) => screen.queryByRole('button', { name });
const dialog = () => screen.getByTestId('AllowAlwaysConfirmDialog');
const editView = () => screen.getByTestId('EditModeView');

const subagent = (extra: ApprovalPayloadData = {}, call = shellCall()) =>
  makeApproval('subagent_approval', { tool_calls: [call], ...extra });

describe('PolymorphicApprovalCard', () => {
  describe('the subagent task id', () => {
    it('is carried by the review layout and the edit layout, the payload one first', async () => {
      const approval = subagent({ subagent_task_id: 'task-payload' });
      approval.subagent_task_id = 'task-approval';
      const { container } = renderCard(approval);
      expect(container.firstElementChild?.getAttribute('data-subagent-task-id')).toBe('task-payload');

      await click(T.edit);
      expect(container.firstElementChild?.getAttribute('data-subagent-task-id')).toBe('task-payload');
    });

    it('falls back to the task id of the approval, and is absent without one', () => {
      const withApprovalId = subagent();
      withApprovalId.subagent_task_id = 'task-approval';
      expect(renderCard(withApprovalId).container.firstElementChild?.getAttribute('data-subagent-task-id')).toBe(
        'task-approval',
      );
      cleanup();

      expect(renderCard(subagent()).container.firstElementChild?.hasAttribute('data-subagent-task-id')).toBe(false);
    });
  });

  describe('the banners', () => {
    it('shows none for an approval nothing is wrong with', () => {
      const { container } = renderCard(subagent());

      expect(screen.queryByTestId('spend-protection-banner')).toBeNull();
      expect(screen.queryByTestId('destructive-confirmation-banner')).toBeNull();
      expect(container.textContent).not.toContain('toolApproval.autoModeSuspended.title');
      expect(container.textContent).not.toContain('toolApproval.sociallyIrreversible.title');
      expect(container.textContent).not.toContain('toolApproval.smartDenied.title');
    });

    it('shows the one each review flag calls for', () => {
      const { container } = renderCard(
        subagent({
          reviewConfigs: [
            { isSpend: true, spendAmount: 3, autoModeSuspended: 'consecutive', sociallyIrreversible: true },
            { smartDenied: true, irreversibleDestructive: true },
          ],
        }),
      );

      expect(screen.getByTestId('spend-protection-banner')).toBeDefined();
      expect(screen.getByTestId('destructive-confirmation-banner')).toBeDefined();
      expect(container.textContent).toContain('toolApproval.autoModeSuspended.consecutiveReason');
      expect(container.textContent).toContain('toolApproval.sociallyIrreversible.title');
      expect(container.textContent).toContain('toolApproval.smartDenied.title');
    });

    it('keeps an irreversible action locked until its banner is confirmed, and unlocks it on CONFIRM', async () => {
      const { onResolve } = renderCard(
        subagent({ reviewConfigs: [{ irreversibleDestructive: true, snapshotId: 'snap-1' }] }),
      );
      const confirm = screen.getByRole('button', { name: 'toolApproval.irreversibleDestructive.confirmButton' });
      expect((confirm as HTMLButtonElement).disabled).toBe(true);

      const input = screen.getByTestId('destructive-confirmation-banner').querySelector('input') as HTMLInputElement;
      fireEvent.change(input, { target: { value: 'CONFIRM' } });
      expect((confirm as HTMLButtonElement).disabled).toBe(false);
      await click('toolApproval.irreversibleDestructive.confirmButton');

      expect(onResolve).toHaveBeenCalledTimes(1);
      expect(onResolve.mock.calls[0][0]).toBe('approve');
    });

    it('locks the confirmation input while a decision is being submitted', () => {
      renderCard(subagent({ reviewConfigs: [{ irreversibleDestructive: true }] }), true);

      const input = screen.getByTestId('destructive-confirmation-banner').querySelector('input') as HTMLInputElement;
      expect(input.disabled).toBe(true);
    });
  });

  describe('the comment', () => {
    it('is sent with a rejection and as guidance with an approval', async () => {
      const { onResolve } = renderCard(subagent());

      fireEvent.change(screen.getByLabelText(T.comment), { target: { value: 'be careful' } });
      await click(T.reject);
      await click(T.approve);

      expect(onResolve.mock.calls[0]).toEqual(['reject', 'be careful', undefined, { feedback: 'be careful' }]);
      expect(onResolve.mock.calls[1][1]).toBe('be careful');
      expect(onResolve.mock.calls[1][3]).toMatchObject({ guidance: 'be careful' });
    });

    it('is bound to the approval it belongs to', () => {
      renderCard(makeApproval('unknown', {}, { approval_id: 'appr-42' }));

      expect(screen.getByLabelText(T.comment).getAttribute('id')).toBe('comment-appr-42');
    });
  });

  describe('the meta bar', () => {
    it('offers the way back to the chat the approval came from', () => {
      renderCard(makeApproval('unknown', {}, { chat_id: 'chat-1' }));

      expect(queryButton('notifications.jumpToChatAria')).not.toBeNull();
    });

    it('is absent for an approval without a chat or expiry', () => {
      renderCard(makeApproval('unknown', {}));

      expect(queryButton('notifications.jumpToChatAria')).toBeNull();
    });
  });

  describe('a tool clarification', () => {
    it('starts the editor from the failed arguments and approves what the editor holds', async () => {
      const { onResolve } = renderCard(makeApproval('tool_clarification', { content: { path: '/a' } as never }));
      const editor = screen.getByTestId('editor') as HTMLTextAreaElement;
      expect(editor.value).toBe(JSON.stringify({ path: '/a' }, null, 2));

      fireEvent.change(editor, { target: { value: '{"path":"/b"}' } });
      await click(T.approve);

      expect(onResolve.mock.calls[0][2]).toEqual({ path: '/b' });
    });

    it('starts the editor from an empty object when the payload has no arguments', () => {
      renderCard(makeApproval('tool_clarification', {}));

      expect((screen.getByTestId('editor') as HTMLTextAreaElement).value).toBe('{}');
    });
  });

  describe('editing a single shell call', () => {
    const open = async (approval = subagent()) => {
      const rendered = renderCard(approval);
      await click(T.edit);
      return rendered;
    };

    it('is offered for one shell call only', () => {
      renderCard(subagentApproval([shellCall(), shellCall({ command: 'pwd' })]));
      expect(queryButton(T.edit)).toBeNull();
      cleanup();

      renderCard(makeApproval('unknown', { tool_calls: [shellCall()] }));
      expect(queryButton(T.edit)).toBeNull();
      cleanup();

      renderCard(subagent());
      expect(queryButton(T.edit)).not.toBeNull();
    });

    it('replaces the review with the edit view that is told what it edits', async () => {
      await open();

      expect(queryButton(T.approve)).toBeNull();
      expect(editView().getAttribute('data-permission-type')).toBe('toolApproval.permissionTypes.codeInterpreter');
      expect(editView().getAttribute('data-tool-name')).toBe('bash_code_execute_tool');
      expect(editView().getAttribute('data-request-id')).toBe('appr-1');
      expect(editView().getAttribute('data-loading')).toBe('false');
      expect(editView().getAttribute('data-hide-allow-always')).toBe('false');
      expect(editView().getAttribute('data-shell-command')).toBe('ls -la');
    });

    it('cannot be opened while a decision is being submitted', () => {
      renderCard(subagent(), true);

      expect((screen.getByRole('button', { name: T.edit }) as HTMLButtonElement).disabled).toBe(true);
    });

    it('tells the edit view while a decision is being submitted', async () => {
      const approval = subagent();
      const { rerender, onResolve } = await open(approval);

      rerender(<PolymorphicApprovalCard approval={approval} onResolve={onResolve} isSubmitting />);

      expect(editView().getAttribute('data-loading')).toBe('true');
    });

    it('hands the edit view the flag that turns standing grants off', async () => {
      await open(subagent({ reviewConfigs: [{ hideAllowAlways: true }] }));

      expect(editView().getAttribute('data-hide-allow-always')).toBe('true');
    });

    it('returns to the review when the edit is cancelled', async () => {
      await open();

      await click('cancel edit');

      expect(screen.queryByTestId('EditModeView')).toBeNull();
      expect(queryButton(T.approve)).not.toBeNull();
    });

    it('approves unchanged arguments and returns to the review', async () => {
      const { onResolve } = await open();

      await click('confirm edit');

      expect(onResolve).toHaveBeenCalledExactlyOnceWith('approve', '', undefined, {
        allow_always: undefined,
        ttl_seconds: undefined,
        guidance: undefined,
      });
      expect(screen.queryByTestId('EditModeView')).toBeNull();
    });

    it('sends changed arguments as an edit', async () => {
      const { onResolve } = await open();

      await click('type edit');
      await click('confirm edit');

      expect(onResolve.mock.calls[0][0]).toBe('edit');
      expect(onResolve.mock.calls[0][3]).toMatchObject({ edited_args: { command: 'echo edited' } });
    });
  });

  describe('always allowing', () => {
    it('is offered for a subagent approval unless a review flag turns standing grants off', () => {
      renderCard(subagent());
      expect(queryButton(T.allowAlways)).not.toBeNull();
      cleanup();

      renderCard(makeApproval('unknown', { tool_calls: [shellCall()] }));
      expect(queryButton(T.allowAlways)).toBeNull();
      cleanup();

      for (const flag of [
        { hideAllowAlways: true },
        { isSpend: true },
        { sociallyIrreversible: true },
        { irreversibleDestructive: true },
      ]) {
        renderCard(subagent({ reviewConfigs: [flag] }));
        expect(queryButton(T.allowAlways)).toBeNull();
        cleanup();
      }
    });

    it('has a dialog for a subagent approval only', () => {
      renderCard(makeApproval('unknown', {}));

      expect(screen.queryByTestId('AllowAlwaysConfirmDialog')).toBeNull();
    });

    it('opens a dialog that starts at the exact-command scope for the primary tool', async () => {
      renderCard(subagent());
      expect(dialog().getAttribute('data-open')).toBe('false');

      await click(T.allowAlways);

      expect(dialog().getAttribute('data-open')).toBe('true');
      expect(dialog().getAttribute('data-scope')).toBe('exact');
      expect(dialog().getAttribute('data-duration')).toBe('session');
      expect(dialog().getAttribute('data-tool-name')).toBe('bash_code_execute_tool');
      expect(dialog().getAttribute('data-shell-command')).toBe('ls -la');
      expect(dialog().getAttribute('data-permission-type')).toBe('toolApproval.permissionTypes.codeInterpreter');
    });

    it('tells the dialog while a decision is being submitted', () => {
      renderCard(subagent(), true);

      expect(dialog().getAttribute('data-loading')).toBe('true');
    });

    it('approves with the scope and duration picked, the comment as guidance, and closes', async () => {
      const { onResolve } = renderCard(subagent());
      fireEvent.change(screen.getByLabelText(T.comment), { target: { value: 'fine' } });
      await click(T.allowAlways);

      await click('pick pattern');
      await click('pick hour');
      await click('confirm allow always');

      expect(onResolve).toHaveBeenCalledExactlyOnceWith('approve', 'fine', undefined, {
        allow_always: scopeToAllowAlwaysValue('pattern', '1h'),
        ttl_seconds: 3600,
        guidance: 'fine',
      });
      expect(dialog().getAttribute('data-open')).toBe('false');
    });

    it('approves without guidance when there is no comment', async () => {
      const { onResolve } = renderCard(subagent());
      await click(T.allowAlways);

      await click('confirm allow always');

      expect(onResolve).toHaveBeenCalledExactlyOnceWith('approve', '', undefined, {
        allow_always: scopeToAllowAlwaysValue('exact', 'session'),
        ttl_seconds: -1,
        guidance: undefined,
      });
    });

    it('closes without deciding anything when it is dismissed', async () => {
      const { onResolve } = renderCard(subagent());
      await click(T.allowAlways);

      await click('close dialog');

      expect(dialog().getAttribute('data-open')).toBe('false');
      expect(onResolve).not.toHaveBeenCalled();
    });

    it.each([
      ['bash_code_execute_tool', 'toolApproval.permissionTypes.codeInterpreter'],
      ['execute_code', 'toolApproval.permissionTypes.codeInterpreter'],
      ['browser_navigate', 'toolApproval.permissionTypes.browser'],
      ['web_search_tool', 'toolApproval.permissionTypes.default'],
    ])('labels the permission of %s as %s', (name, label) => {
      renderCard(subagent({}, { name, args: { command: 'x' } }));

      expect(dialog().getAttribute('data-permission-type')).toBe(label);
    });

    it('starts the tool-wide scope for a tool that is not a shell, and calls it "unknown" without tool calls', () => {
      renderCard(subagent({}, { name: 'web_search_tool', args: { query: 'q' } }));
      expect(dialog().getAttribute('data-scope')).toBe('tool');
      cleanup();

      renderCard(subagentApproval([]));
      expect(dialog().getAttribute('data-tool-name')).toBe('unknown');
      expect(dialog().getAttribute('data-permission-type')).toBe('toolApproval.permissionTypes.default');
    });
  });
});
