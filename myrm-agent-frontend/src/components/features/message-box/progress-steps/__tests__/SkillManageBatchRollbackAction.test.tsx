import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import type { MockLocale } from '@/test-utils/realIntl';
import enMessages from '../../../../../../locales/en.json';
import zhMessages from '../../../../../../locales/zh.json';
import { SkillManageBatchRollbackAction } from '../SkillManageBatchRollbackAction';

const locale = vi.hoisted(() => ({ current: 'en' as MockLocale }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => locale.current));

const mocks = vi.hoisted(() => ({
  rollback: vi.fn(),
  fetchMarketSkills: vi.fn(),
  fetchLocalSkills: vi.fn(),
  notifySkillContentChanged: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('@/services/skill/optimization', () => ({ rollbackSkillMutationBatch: mocks.rollback }));
vi.mock('@/store/skill', () => ({
  useSkillStore: (select: (state: Record<string, unknown>) => unknown) =>
    select({ fetchMarketSkills: mocks.fetchMarketSkills, fetchLocalSkills: mocks.fetchLocalSkills }),
}));
vi.mock('@/lib/skills/skillContentSync', () => ({ notifySkillContentChanged: mocks.notifySkillContentChanged }));
vi.mock('@/lib/utils/toast', () => ({ toast: { success: mocks.toastSuccess, error: mocks.toastError } }));

type RollbackResult = { batch_id: string; skills_restored: number; status: string };

const LANGUAGES: readonly MockLocale[] = ['en', 'zh'];
const BUNDLES = { en: enMessages, zh: zhMessages };

const copy = (language: MockLocale) => BUNDLES[language].progressSteps;

/** The server answers 4xx with `detail: {code, message}`; `apiRequest` exposes that object as `ApiError.data`. */
function apiFailure(status: number, code?: string): ApiError {
  const error = new ApiError('rollback request failed', status);
  if (code) {
    error.data = { code, message: 'server detail' };
  }
  return error;
}

async function openConfirmation(language: MockLocale) {
  locale.current = language;
  const user = userEvent.setup();
  render(<SkillManageBatchRollbackAction batchId="batch-1" />);
  await user.click(screen.getByTestId('skill-manage-rollback-button'));
  return user;
}

describe('SkillManageBatchRollbackAction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.fetchMarketSkills.mockResolvedValue(undefined);
    mocks.fetchLocalSkills.mockResolvedValue(undefined);
  });

  describe.each(LANGUAGES)('in %s', (language) => {
    it('undoes the batch, refreshes the skill lists and reports how many skills were restored', async () => {
      mocks.rollback.mockResolvedValue({ batch_id: 'batch-1', skills_restored: 2, status: 'rolled_back' });
      const user = await openConfirmation(language);

      await user.click(screen.getByTestId('skill-manage-rollback-confirm'));

      await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledTimes(1));
      expect(mocks.rollback).toHaveBeenCalledTimes(1);
      expect(mocks.rollback).toHaveBeenCalledWith('batch-1');
      expect(mocks.fetchMarketSkills).toHaveBeenCalledWith(true);
      expect(mocks.fetchLocalSkills).toHaveBeenCalledTimes(1);
      expect(mocks.notifySkillContentChanged).toHaveBeenCalledTimes(1);
      expect(mocks.toastSuccess.mock.calls[0]?.[0]).toBe(
        copy(language).skillManageRollbackSuccess.replace('{count}', '2'),
      );
      expect(mocks.toastError).not.toHaveBeenCalled();

      const button = screen.getByTestId('skill-manage-rollback-button');
      expect(button).toBeDisabled();
      expect(button).toHaveTextContent(copy(language).skillManageRollbackDone);
      expect(screen.queryByTestId('skill-manage-rollback-confirm')).not.toBeInTheDocument();
    });

    it.each([
      [
        'a batch that was already undone',
        apiFailure(409, 'batch_already_consumed'),
        'skillManageRollbackAlreadyConsumed',
      ],
      [
        'an undo that could not restore safely',
        apiFailure(409, 'compensation_failed'),
        'skillManageRollbackCompensationFailed',
      ],
      ['a rollback the server refused', apiFailure(409, 'rollback_failed'), 'skillManageRollbackFailed'],
      ['a busy database', apiFailure(503), 'skillManageRollbackFailed'],
      ['a lost connection', new TypeError('Failed to fetch'), 'skillManageRollbackFailed'],
    ] as const)(
      'tells the user what happened after %s and leaves the undo retryable',
      async (_case, failure, messageKey) => {
        mocks.rollback.mockRejectedValue(failure);
        const user = await openConfirmation(language);

        await user.click(screen.getByTestId('skill-manage-rollback-confirm'));

        await waitFor(() => expect(mocks.toastError).toHaveBeenCalledTimes(1));
        expect(mocks.toastError.mock.calls[0]?.[0]).toBe(copy(language)[messageKey]);
        expect(mocks.toastSuccess).not.toHaveBeenCalled();
        expect(mocks.fetchMarketSkills).not.toHaveBeenCalled();
        expect(mocks.fetchLocalSkills).not.toHaveBeenCalled();
        expect(mocks.notifySkillContentChanged).not.toHaveBeenCalled();
        expect(screen.getByTestId('skill-manage-rollback-confirm')).toBeEnabled();
        expect(screen.getByTestId('skill-manage-rollback-button')).not.toHaveTextContent(
          copy(language).skillManageRollbackDone,
        );
      },
    );
  });

  it('sends the undo once when the confirm button is pressed again while the request is running', async () => {
    let finish: (result: RollbackResult) => void = () => {};
    mocks.rollback.mockReturnValue(
      new Promise<RollbackResult>((resolve) => {
        finish = resolve;
      }),
    );
    const user = await openConfirmation('en');
    const confirm = screen.getByTestId('skill-manage-rollback-confirm');

    await user.click(confirm);
    await user.click(confirm);

    expect(mocks.rollback).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('skill-manage-rollback-button')).toHaveTextContent(
      copy('en').skillManageRollbackSubmitting,
    );

    await act(async () => {
      finish({ batch_id: 'batch-1', skills_restored: 1, status: 'rolled_back' });
    });
    await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledTimes(1));
    expect(mocks.rollback).toHaveBeenCalledTimes(1);
  });

  it('closes the confirmation without undoing anything when the user cancels', async () => {
    const user = await openConfirmation('en');

    await user.click(screen.getByRole('button', { name: enMessages.settings.skills.upload.cancel }));

    await waitFor(() => expect(screen.queryByTestId('skill-manage-rollback-confirm')).not.toBeInTheDocument());
    expect(mocks.rollback).not.toHaveBeenCalled();
    expect(screen.getByTestId('skill-manage-rollback-button')).toBeEnabled();
  });
});
