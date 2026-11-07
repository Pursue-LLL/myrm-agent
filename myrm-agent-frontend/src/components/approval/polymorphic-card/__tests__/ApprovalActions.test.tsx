import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DestructiveUndoCard } from '@/components/approval/DestructiveUndoCard';
import { ApprovalActions } from '../ApprovalActions';
import type { ApprovalFlags } from '../approvalFlags';
import { makeApproval, noFlags } from './approvalKit';

const mocks = vi.hoisted(() => ({
  toast: { custom: vi.fn(), dismiss: vi.fn() },
}));

vi.mock('next-intl', async () => (await import('./approvalStubs')).nextIntlModule);
vi.mock('sonner', () => ({ toast: mocks.toast }));

const RESOLVE = {
  reject: 'toolApproval.reject',
  approve: 'toolApproval.approve',
  confirmDestructive: 'toolApproval.irreversibleDestructive.confirmButton',
  override: 'toolApproval.smartDenied.overrideOnce',
  edit: 'toolApproval.edit',
  allowAlways: 'toolApproval.allowAlways',
};

type Variant = 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost';

interface UndoCardProps {
  approvalId: string;
  snapshotId: string;
  onRollbackSuccess: () => void;
}

/** The classes that tell the Button variants apart, in the order they are checked. */
const VARIANT_MARKERS: ReadonlyArray<readonly [string, Variant]> = [
  ['bg-destructive', 'destructive'],
  ['btn-brand-elevation', 'default'],
  ['border-input', 'outline'],
  ['bg-secondary', 'secondary'],
];

/** The Button variant a rendered button was built with, read back from its distinguishing classes. */
const variantOf = (button: HTMLElement): Variant =>
  VARIANT_MARKERS.find(([marker]) => button.className.includes(marker))?.[1] ?? 'ghost';

const button = (name: string) => screen.getByRole('button', { name }) as HTMLButtonElement;
const press = async (name: string) => {
  await act(async () => {
    fireEvent.click(button(name));
  });
};

const handlers = () => ({
  onResolve: vi.fn().mockResolvedValue(undefined),
  onEdit: vi.fn(),
  onAllowAlways: vi.fn(),
});

interface RenderOptions {
  approval?: ReturnType<typeof makeApproval>;
  comment?: string;
  editedArgs?: string;
  flags?: Partial<ApprovalFlags>;
  destructiveConfirmed?: boolean;
  isSubmitting?: boolean;
  canEditShell?: boolean;
  canAllowAlways?: boolean;
}

const renderActions = (options: RenderOptions = {}) => {
  const fns = handlers();
  render(
    <ApprovalActions
      approval={options.approval ?? makeApproval('subagent_approval')}
      comment={options.comment ?? ''}
      editedArgs={options.editedArgs ?? ''}
      flags={{ ...noFlags, ...options.flags }}
      destructiveConfirmed={options.destructiveConfirmed ?? false}
      isSubmitting={options.isSubmitting ?? false}
      canEditShell={options.canEditShell ?? false}
      canAllowAlways={options.canAllowAlways ?? false}
      {...fns}
    />,
  );
  return fns;
};

const destructive = {
  isIrreversibleDestructive: true,
  destructiveSnapshotId: 'snap-1',
} satisfies Partial<ApprovalFlags>;

describe('ApprovalActions', () => {
  beforeEach(() => {
    mocks.toast.custom.mockClear();
    mocks.toast.dismiss.mockClear();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  describe('a regular approval', () => {
    it('offers reject and approve only, as an outline and a default button', () => {
      renderActions();

      expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual([RESOLVE.reject, RESOLVE.approve]);
      expect(variantOf(button(RESOLVE.reject))).toBe('outline');
      expect(variantOf(button(RESOLVE.approve))).toBe('default');
    });

    it('rejects with the comment as feedback, or without feedback when there is none', async () => {
      const withComment = renderActions({ comment: 'too risky' });
      await press(RESOLVE.reject);
      expect(withComment.onResolve).toHaveBeenCalledExactlyOnceWith('reject', 'too risky', undefined, {
        feedback: 'too risky',
      });
      cleanup();

      const withoutComment = renderActions();
      await press(RESOLVE.reject);
      expect(withoutComment.onResolve).toHaveBeenCalledExactlyOnceWith('reject', '', undefined, {
        feedback: undefined,
      });
    });

    it('approves with the comment as guidance and the spend digest of the action', async () => {
      const fns = renderActions({
        comment: 'go ahead',
        flags: { spendConfig: { amount: 5, currency: 'USD', actionDigest: 'digest-7' } },
      });

      await press(RESOLVE.approve);

      expect(fns.onResolve).toHaveBeenCalledExactlyOnceWith('approve', 'go ahead', undefined, {
        guidance: 'go ahead',
        action_digest: 'digest-7',
        actionDigest: 'digest-7',
      });
    });

    it('approves without guidance or digest when there is neither', async () => {
      const fns = renderActions();

      await press(RESOLVE.approve);

      expect(fns.onResolve).toHaveBeenCalledExactlyOnceWith('approve', '', undefined, {
        guidance: undefined,
        action_digest: undefined,
        actionDigest: undefined,
      });
    });

    it('shows edit and always-allow only when the card allows them, and hands the click on', () => {
      const none = renderActions();
      expect(screen.queryByRole('button', { name: RESOLVE.edit })).toBeNull();
      expect(screen.queryByRole('button', { name: RESOLVE.allowAlways })).toBeNull();
      expect(none.onEdit).not.toHaveBeenCalled();
      cleanup();

      const both = renderActions({ canEditShell: true, canAllowAlways: true });
      expect(variantOf(button(RESOLVE.edit))).toBe('secondary');
      expect(variantOf(button(RESOLVE.allowAlways))).toBe('ghost');
      fireEvent.click(button(RESOLVE.edit));
      fireEvent.click(button(RESOLVE.allowAlways));
      expect(both.onEdit).toHaveBeenCalledTimes(1);
      expect(both.onAllowAlways).toHaveBeenCalledTimes(1);
      expect(both.onResolve).not.toHaveBeenCalled();
    });

    it('disables every decision while a decision is being submitted', () => {
      renderActions({ isSubmitting: true, canEditShell: true, canAllowAlways: true });

      for (const name of [RESOLVE.reject, RESOLVE.edit, RESOLVE.allowAlways, RESOLVE.approve]) {
        expect(button(name).disabled).toBe(true);
      }
    });

    it('leaves every decision enabled otherwise', () => {
      renderActions({ canEditShell: true, canAllowAlways: true });

      for (const name of [RESOLVE.reject, RESOLVE.edit, RESOLVE.allowAlways, RESOLVE.approve]) {
        expect(button(name).disabled).toBe(false);
      }
    });
  });

  describe('a tool clarification', () => {
    const clarification = makeApproval('tool_clarification');

    it('approves a retry with the arguments the user fixed', async () => {
      const fns = renderActions({ approval: clarification, comment: 'fixed', editedArgs: '{"path":"/tmp/a"}' });

      await press(RESOLVE.approve);

      expect(fns.onResolve).toHaveBeenCalledExactlyOnceWith(
        'approve',
        'fixed',
        { path: '/tmp/a' },
        {
          guidance: 'fixed',
          action_digest: undefined,
          actionDigest: undefined,
        },
      );
    });

    it('does not approve while the fixed arguments are not valid JSON', async () => {
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
      const fns = renderActions({ approval: clarification, editedArgs: '{"path": ' });

      await press(RESOLVE.approve);

      expect(fns.onResolve).not.toHaveBeenCalled();
      expect(consoleError).toHaveBeenCalledExactlyOnceWith('Invalid JSON payload');
    });

    it('ignores the editor text for any other approval', async () => {
      const fns = renderActions({ editedArgs: '{"path":"/tmp/a"}' });

      await press(RESOLVE.approve);

      expect(fns.onResolve.mock.calls[0][2]).toBeUndefined();
    });
  });

  describe('an irreversible destructive action', () => {
    it('swaps approve for a destructive confirm button that stays locked until the user confirmed', () => {
      renderActions({ flags: destructive });

      expect(screen.queryByRole('button', { name: RESOLVE.approve })).toBeNull();
      expect(variantOf(button(RESOLVE.confirmDestructive))).toBe('destructive');
      expect(button(RESOLVE.confirmDestructive).disabled).toBe(true);
      expect(button(RESOLVE.reject).disabled).toBe(false);
    });

    it('does not resolve while locked', async () => {
      const fns = renderActions({ flags: destructive });

      await press(RESOLVE.confirmDestructive);

      expect(fns.onResolve).not.toHaveBeenCalled();
      expect(mocks.toast.custom).not.toHaveBeenCalled();
    });

    it('approves once confirmed and offers a ten-minute undo for the snapshot', async () => {
      const fns = renderActions({
        approval: makeApproval('subagent_approval', undefined, { approval_id: 'appr-9' }),
        flags: destructive,
        destructiveConfirmed: true,
      });

      await press(RESOLVE.confirmDestructive);

      expect(fns.onResolve).toHaveBeenCalledTimes(1);
      expect(fns.onResolve.mock.calls[0][0]).toBe('approve');
      expect(mocks.toast.custom).toHaveBeenCalledExactlyOnceWith(expect.any(Function), {
        duration: 10 * 60 * 1000,
        id: 'destructive-undo-appr-9',
      });
      expect(fns.onResolve.mock.invocationCallOrder[0]).toBeLessThan(mocks.toast.custom.mock.invocationCallOrder[0]);
    });

    it('builds an undo card for this approval and snapshot that dismisses its own toast on success', async () => {
      renderActions({
        approval: makeApproval('subagent_approval', undefined, { approval_id: 'appr-9' }),
        flags: destructive,
        destructiveConfirmed: true,
      });
      await press(RESOLVE.confirmDestructive);

      const renderToast = mocks.toast.custom.mock.calls[0][0] as (toastId: string) => ReactElement<UndoCardProps>;
      const card = renderToast('toast-1');

      expect(card.type).toBe(DestructiveUndoCard);
      expect(card.props).toMatchObject({ approvalId: 'appr-9', snapshotId: 'snap-1' });
      card.props.onRollbackSuccess();
      expect(mocks.toast.dismiss).toHaveBeenCalledExactlyOnceWith('toast-1');
    });

    it('offers no undo when no snapshot was taken', async () => {
      const fns = renderActions({
        flags: { isIrreversibleDestructive: true },
        destructiveConfirmed: true,
      });

      await press(RESOLVE.confirmDestructive);

      expect(fns.onResolve).toHaveBeenCalledTimes(1);
      expect(mocks.toast.custom).not.toHaveBeenCalled();
    });

    it('offers no undo for an action that can be taken back', async () => {
      renderActions({ flags: { destructiveSnapshotId: 'snap-1' } });

      await press(RESOLVE.approve);

      expect(mocks.toast.custom).not.toHaveBeenCalled();
    });

    it('stays locked while a decision is being submitted, even when confirmed', () => {
      renderActions({ flags: destructive, destructiveConfirmed: true, isSubmitting: true });

      expect(button(RESOLVE.confirmDestructive).disabled).toBe(true);
    });
  });

  describe('an action the safety review refused', () => {
    const denied = { hasAnySmartDenied: true } satisfies Partial<ApprovalFlags>;

    it('offers a destructive reject and an outline override once, and no other decision', () => {
      renderActions({ flags: denied, canEditShell: true, canAllowAlways: true });

      expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual([RESOLVE.reject, RESOLVE.override]);
      expect(variantOf(button(RESOLVE.reject))).toBe('destructive');
      expect(variantOf(button(RESOLVE.override))).toBe('outline');
    });

    it('rejects with the comment as feedback, or without feedback when there is none', async () => {
      const withComment = renderActions({ flags: denied, comment: 'no' });
      await press(RESOLVE.reject);
      expect(withComment.onResolve).toHaveBeenCalledExactlyOnceWith('reject', 'no', undefined, { feedback: 'no' });
      cleanup();

      const withoutComment = renderActions({ flags: denied });
      await press(RESOLVE.reject);
      expect(withoutComment.onResolve).toHaveBeenCalledExactlyOnceWith('reject', '', undefined, {
        feedback: undefined,
      });
    });

    it('overrides once with the comment as guidance and the spend digest', async () => {
      const fns = renderActions({
        flags: { ...denied, spendConfig: { currency: 'USD', actionDigest: 'digest-3' } },
        comment: 'I know',
      });

      await press(RESOLVE.override);

      expect(fns.onResolve).toHaveBeenCalledExactlyOnceWith('approve', 'I know', undefined, {
        guidance: 'I know',
        action_digest: 'digest-3',
        actionDigest: 'digest-3',
      });
    });

    it('overrides once without guidance or digest when there is neither', async () => {
      const fns = renderActions({ flags: denied });

      await press(RESOLVE.override);

      expect(fns.onResolve).toHaveBeenCalledExactlyOnceWith('approve', '', undefined, {
        guidance: undefined,
        action_digest: undefined,
        actionDigest: undefined,
      });
    });

    it('locks the override while submitting, or while an irreversible action is unconfirmed', () => {
      renderActions({ flags: { ...denied, isIrreversibleDestructive: true } });
      expect(button(RESOLVE.override).disabled).toBe(true);
      cleanup();

      renderActions({ flags: { ...denied, isIrreversibleDestructive: true }, destructiveConfirmed: true });
      expect(button(RESOLVE.override).disabled).toBe(false);
      cleanup();

      renderActions({ flags: denied, isSubmitting: true });
      expect(button(RESOLVE.override).disabled).toBe(true);
      expect(button(RESOLVE.reject).disabled).toBe(true);
    });
  });
});
