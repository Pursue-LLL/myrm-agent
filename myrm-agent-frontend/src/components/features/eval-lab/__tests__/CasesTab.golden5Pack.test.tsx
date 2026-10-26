/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { confirmAction } from '@/lib/app-dialog';
import { getGolden5PackJson } from '../constants/golden5PackTemplate';
import CasesTab from '../tabs/CasesTab';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('@/lib/app-dialog', () => ({ confirmAction: vi.fn() }));
vi.mock('@/components/features/app-shell/lazy-monaco-editor', () => ({ LazyMonacoEditor: () => null }));
vi.mock('../components/CaseFormatReference', () => ({ default: () => null }));

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

const loadButton = () => screen.getByRole('button', { name: 'golden5Pack.loadButton' });

describe('CasesTab Golden 5-Pack loader', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each([
    ['empty', ''],
    ['blank', '  \n '],
  ])('loads the template straight into an %s editor without asking', async (_label, draft) => {
    const onDraftChange = vi.fn();
    render(<CasesTab casesDraft={draft} onDraftChange={onDraftChange} />);

    fireEvent.click(loadButton());

    await waitFor(() => expect(onDraftChange).toHaveBeenCalledExactlyOnceWith(getGolden5PackJson(true)));
    expect(confirmAction).not.toHaveBeenCalled();
  });

  it('asks before replacing existing cases and loads the template once the user agrees', async () => {
    vi.mocked(confirmAction).mockResolvedValue(true);
    const onDraftChange = vi.fn();
    render(<CasesTab casesDraft='[{"message":"mine"}]' onDraftChange={onDraftChange} />);

    fireEvent.click(loadButton());

    await waitFor(() => expect(onDraftChange).toHaveBeenCalledExactlyOnceWith(getGolden5PackJson(true)));
    expect(confirmAction).toHaveBeenCalledExactlyOnceWith({
      variant: 'warning',
      description: 'golden5Pack.loadConfirm',
      confirmText: 'golden5Pack.loadConfirmAction',
    });
  });

  it('keeps the existing cases when the user declines', async () => {
    vi.mocked(confirmAction).mockResolvedValue(false);
    const onDraftChange = vi.fn();
    render(<CasesTab casesDraft='[{"message":"mine"}]' onDraftChange={onDraftChange} />);

    fireEvent.click(loadButton());
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(1));
    await settle();

    expect(onDraftChange).not.toHaveBeenCalled();
  });
});
