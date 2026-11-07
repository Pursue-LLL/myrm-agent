// @vitest-environment jsdom
import { act, cleanup, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { CronJob } from '@/services/cron.types';
import {
  button,
  click,
  createJob,
  createdJobOf,
  fillValidJob,
  openCustom,
  openDialog,
  placeholder,
  prepareAudit,
  resetKit,
  setDialogOpen,
  settle,
  state,
  submit,
  toast,
  typeInto,
} from './createDialogTestKit';

beforeEach(resetKit);
afterEach(cleanup);

describe('create button', () => {
  it('stays disabled until there is text and a schedule', async () => {
    await openCustom();
    expect(button('createSubmit')).toBeDisabled();

    await typeInto(placeholder('createPromptPlaceholder'), 'Summarise the news');
    expect(button('createSubmit')).toBeDisabled();

    await typeInto(placeholder('createCronPlaceholder'), '0 9 * * *');
    expect(button('createSubmit')).toBeEnabled();

    await typeInto(placeholder('createPromptPlaceholder'), '   ');
    expect(button('createSubmit')).toBeDisabled();
    await submit();
    expect(createJob).not.toHaveBeenCalled();
  });

  it('blocks a second request and cancelling while one is in flight', async () => {
    let finish: (job: CronJob) => void = () => undefined;
    createJob.mockImplementation(
      () =>
        new Promise<CronJob>((resolve) => {
          finish = resolve;
        }),
    );
    await fillValidJob();
    await submit();

    expect(button('createSubmit')).toBeDisabled();
    expect(button('cancel')).toBeDisabled();
    await submit();
    expect(createJob).toHaveBeenCalledTimes(1);

    await act(async () => finish(createdJobOf('job-1')));
    expect(screen.getByTestId('audit-panel')).toBeInTheDocument();
  });
});

describe('after the request', () => {
  it('announces the new job and shows its audit panel instead of the form', async () => {
    createJob.mockResolvedValue(createdJobOf('job-7', { name: 'Morning brief' }));
    await fillValidJob();
    await submit();

    expect(prepareAudit).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ id: 'job-7' }));
    expect(toast.success).toHaveBeenCalledExactlyOnceWith('createSuccess');
    expect(screen.getByTestId('audit-panel')).toHaveAttribute('data-job', 'job-7');
    expect(screen.queryByPlaceholderText('createPromptPlaceholder')).toBeNull();
    expect(screen.queryByTestId('cron-create-mode-custom')).toBeNull();
  });

  it('follows the job the audit panel reports', async () => {
    await fillValidJob();
    await submit();
    await click(button('audit-change'));

    expect(screen.getByText('renamed by audit')).toBeInTheDocument();
  });

  it('closes and starts over once the audit allows finishing', async () => {
    const { onOpenChange } = await fillValidJob();
    await submit();
    expect(button('auditDone')).toBeEnabled();
    expect(button('auditDone')).not.toHaveAttribute('title');

    await click(button('auditDone'));

    expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
    expect(screen.queryByTestId('audit-panel')).toBeNull();
    expect(screen.getByText('pick-blueprint')).toBeInTheDocument();
    await click(screen.getByTestId('cron-create-mode-custom'));
    expect(placeholder('createPromptPlaceholder')).toHaveValue('');
  });

  it('keeps finishing disabled, with a hint, until the audit allows it', async () => {
    state.canDismissAudit = false;
    await fillValidJob();
    await submit();

    expect(button('auditDone')).toBeDisabled();
    expect(button('auditDone')).toHaveAttribute('title', 'auditDoneHint');
  });
});

describe('when the request fails', () => {
  const expectFormKept = () => {
    expect(placeholder('createPromptPlaceholder')).toHaveValue('Summarise the news');
    expect(button('createSubmit')).toBeEnabled();
    expect(screen.queryByTestId('audit-panel')).toBeNull();
  };

  it('tells the user and keeps the form so the request can be retried', async () => {
    createJob.mockRejectedValueOnce(new Error('boom'));
    await fillValidJob();
    await submit();

    expect(toast.error).toHaveBeenCalledExactlyOnceWith('actionFail');
    expect(toast.success).not.toHaveBeenCalled();
    expectFormKept();

    await submit();
    expect(screen.getByTestId('audit-panel')).toBeInTheDocument();
  });

  it('stays silent when the server already explained that the job was held back', async () => {
    createJob.mockRejectedValueOnce(Object.assign(new Error('held'), { riskHeld: true }));
    await fillValidJob();
    await submit();

    expect(toast.error).not.toHaveBeenCalled();
    expectFormKept();
  });

  it('warns when the new job could not be paused for its audit', async () => {
    prepareAudit.mockRejectedValueOnce(new Error('pause failed'));
    await fillValidJob();
    await submit();

    expect(toast.error).toHaveBeenCalledExactlyOnceWith('auditPauseFail');
    expect(toast.success).not.toHaveBeenCalled();
    expectFormKept();
  });
});

describe('closing', () => {
  const expectBackOnTemplates = async () => {
    expect(screen.getByText('pick-blueprint')).toBeInTheDocument();
    await click(screen.getByTestId('cron-create-mode-custom'));
    expect(placeholder('createPromptPlaceholder')).toHaveValue('');
    expect(placeholder('createCronPlaceholder')).toHaveValue('');
  };

  it('starts over when the user cancels', async () => {
    const { onOpenChange } = await fillValidJob();
    await click(button('cancel'));

    expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
    await expectBackOnTemplates();
  });

  it('starts over when the dialog is dismissed', async () => {
    const { onOpenChange } = await fillValidJob();
    await userEvent.setup().keyboard('{Escape}');
    await settle();

    expect(onOpenChange).toHaveBeenCalledWith(false);
    await expectBackOnTemplates();
  });

  it('binds a job to the chat the dialog is opened for, even if it was mounted without one', async () => {
    const opened = await openDialog({ open: false });
    await setDialogOpen(opened, true, { presetChatId: 'c9', presetChatTitle: 'Standup' });
    await click(screen.getByTestId('cron-create-mode-custom'));
    await typeInto(placeholder('createPromptPlaceholder'), 'Summarise the news');
    await typeInto(placeholder('createCronPlaceholder'), '0 9 * * *');
    await submit();

    expect(createJob.mock.calls[0]?.[0]).toMatchObject({ session_target: 'main', chat_id: 'c9' });
  });
});

describe('template tab', () => {
  it('opens on the blueprint catalog', async () => {
    await openDialog();

    expect(screen.getByText('pick-blueprint')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('createPromptPlaceholder')).toBeNull();
  });

  it('fills the picked blueprint inline and goes back to the catalog', async () => {
    await openDialog();
    await click(button('pick-blueprint'));
    expect(screen.getByTestId('inline-fill')).toHaveAttribute('data-blueprint', 'daily');
    expect(screen.queryByText('pick-blueprint')).toBeNull();

    await click(button('blueprint-back'));
    expect(screen.getByText('pick-blueprint')).toBeInTheDocument();
  });

  it('shows the audit panel of a job created from a blueprint', async () => {
    await openDialog();
    await click(button('pick-blueprint'));
    await click(button('blueprint-created'));

    expect(screen.getByTestId('audit-panel')).toHaveAttribute('data-job', 'blueprint-job');
    expect(screen.queryByTestId('inline-fill')).toBeNull();
  });

  it('keeps what was typed on the custom tab while the user looks at the templates', async () => {
    await fillValidJob();
    await click(screen.getByTestId('cron-create-mode-template'));
    await click(screen.getByTestId('cron-create-mode-custom'));

    expect(placeholder('createPromptPlaceholder')).toHaveValue('Summarise the news');
  });
});
