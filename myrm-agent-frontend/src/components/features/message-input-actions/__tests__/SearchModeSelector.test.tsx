/**
 * The mode picker asks the search-service gate before it lets a user into the fast search mode, keeps the mode the
 * gate refuses, and lets only the latest click decide the mode while a slower gate answer is still on its way. The modes
 * are radios of one group: the checked one holds the tab stop, arrow keys move focus, and pressing a mode switches to it.
 */
import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { deferred } from '@/test-utils/deferred';
import SearchModeSelector from '../SearchModeSelector';

const gate = vi.hoisted(() => ({ checkSearchServiceReady: vi.fn<() => Promise<boolean>>() }));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: () => null,
}));

vi.mock('@/store/config/searchServiceReady', () => ({
  checkSearchServiceReady: gate.checkSearchServiceReady,
}));

describe('SearchModeSelector', () => {
  const setActionMode = vi.fn();

  const pick = async (mode: 'fast' | 'agent') => {
    await act(async () => {
      fireEvent.click(screen.getByRole('radio', { name: `${mode}Title` }));
    });
  };

  beforeEach(() => {
    setActionMode.mockReset();
    gate.checkSearchServiceReady.mockReset().mockResolvedValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('switches to the fast mode once the gate lets it through', async () => {
    render(<SearchModeSelector actionMode="agent" setActionMode={setActionMode} />);

    await pick('fast');

    expect(gate.checkSearchServiceReady).toHaveBeenCalledTimes(1);
    expect(setActionMode).toHaveBeenCalledWith('fast');
  });

  it('keeps the mode the gate refuses', async () => {
    gate.checkSearchServiceReady.mockResolvedValue(false);
    render(<SearchModeSelector actionMode="agent" setActionMode={setActionMode} />);

    await pick('fast');

    expect(gate.checkSearchServiceReady).toHaveBeenCalledTimes(1);
    expect(setActionMode).not.toHaveBeenCalled();
  });

  it('switches to the agent mode without asking the gate', async () => {
    render(<SearchModeSelector actionMode="fast" setActionMode={setActionMode} />);

    await pick('agent');

    expect(setActionMode).toHaveBeenCalledWith('agent');
    expect(gate.checkSearchServiceReady).not.toHaveBeenCalled();
  });

  it('does not ask the gate again for the mode it is already in', async () => {
    render(<SearchModeSelector actionMode="fast" setActionMode={setActionMode} />);

    await pick('fast');

    expect(gate.checkSearchServiceReady).not.toHaveBeenCalled();
    expect(setActionMode).toHaveBeenCalledWith('fast');
  });

  it('drops the answer of a click that a later click has already replaced', async () => {
    const slowGate = deferred<boolean>();
    gate.checkSearchServiceReady.mockReturnValue(slowGate.promise);
    render(<SearchModeSelector actionMode="agent" setActionMode={setActionMode} />);

    await pick('fast');
    await pick('agent');
    await act(async () => {
      slowGate.resolve(true);
    });

    expect(setActionMode.mock.calls).toEqual([['agent']]);
  });

  it('lets only the latest of two clicks on the fast mode set it, whichever answer comes back first', async () => {
    const firstAnswer = deferred<boolean>();
    const secondAnswer = deferred<boolean>();
    gate.checkSearchServiceReady.mockReturnValueOnce(firstAnswer.promise).mockReturnValueOnce(secondAnswer.promise);
    render(<SearchModeSelector actionMode="agent" setActionMode={setActionMode} />);

    await pick('fast');
    await pick('fast');
    await act(async () => {
      secondAnswer.resolve(true);
    });
    await act(async () => {
      firstAnswer.resolve(true);
    });

    expect(setActionMode.mock.calls).toEqual([['fast']]);
  });

  it('marks the current mode as the checked radio', () => {
    render(<SearchModeSelector actionMode="agent" setActionMode={setActionMode} />);

    expect(screen.getByRole('radio', { name: 'agentTitle' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: 'fastTitle' })).toHaveAttribute('aria-checked', 'false');
  });

  it('moves focus between the modes with the arrow keys without switching', async () => {
    const user = userEvent.setup();
    render(<SearchModeSelector actionMode="agent" setActionMode={setActionMode} />);

    await user.tab();
    expect(screen.getByRole('radio', { name: 'agentTitle' })).toHaveFocus();

    await user.keyboard('{ArrowLeft}');

    expect(screen.getByRole('radio', { name: 'fastTitle' })).toHaveFocus();
    expect(setActionMode).not.toHaveBeenCalled();
  });

  it('asks the gate when a mode is pressed with the keyboard', async () => {
    const user = userEvent.setup();
    render(<SearchModeSelector actionMode="agent" setActionMode={setActionMode} />);

    await user.tab();
    await user.keyboard('{ArrowLeft}{Enter}');

    expect(gate.checkSearchServiceReady).toHaveBeenCalledTimes(1);
    expect(setActionMode).toHaveBeenCalledWith('fast');
  });
});
