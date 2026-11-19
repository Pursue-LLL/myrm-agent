/**
 * The mode picker lets a user into the fast search mode only on a synced search service list: it waits for the sync
 * before it judges, and an account that really has none gets the setup notice instead of the mode.
 */
import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { toast } from '@/lib/utils/toast';
import useConfigStore from '@/store/useConfigStore';
import SearchModeSelector from '../SearchModeSelector';

const sync = vi.hoisted(() => ({ ensureSearchServicesLoaded: vi.fn<() => Promise<void>>() }));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: () => null,
}));

vi.mock('@/store/config/searchService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/store/config/searchService')>();
  return { ...actual, ensureSearchServicesLoaded: sync.ensureSearchServicesLoaded };
});

const SEARCH_SERVICE = {
  id: 'svc-1',
  enabled: true,
  priority: 1,
  search_service: 'tavily',
  api_key: 'key',
  createdAt: 1,
};

describe('SearchModeSelector', () => {
  const setActionMode = vi.fn();

  const pick = async (mode: 'fast' | 'agent') => {
    await act(async () => {
      fireEvent.click(screen.getByRole('radio', { name: `${mode}Title` }));
    });
  };

  beforeEach(() => {
    setActionMode.mockReset();
    useConfigStore.setState({ searchServiceConfigs: [] });
    vi.spyOn(toast, 'warning').mockReturnValue(0);
    sync.ensureSearchServicesLoaded.mockReset().mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('switches to the fast mode on the list it waited for', async () => {
    sync.ensureSearchServicesLoaded.mockImplementation(async () => {
      await Promise.resolve();
      useConfigStore.setState({ searchServiceConfigs: [SEARCH_SERVICE] });
    });
    render(<SearchModeSelector actionMode="agent" setActionMode={setActionMode} />);

    await pick('fast');

    expect(setActionMode).toHaveBeenCalledWith('fast');
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it('keeps the mode and shows the setup notice for an account that has no search service', async () => {
    render(<SearchModeSelector actionMode="agent" setActionMode={setActionMode} />);

    await pick('fast');

    expect(sync.ensureSearchServicesLoaded).toHaveBeenCalledTimes(1);
    expect(toast.warning).toHaveBeenCalledTimes(1);
    expect(setActionMode).not.toHaveBeenCalled();
  });

  it('switches to the agent mode without waiting for the search services', async () => {
    render(<SearchModeSelector actionMode="fast" setActionMode={setActionMode} />);

    await pick('agent');

    expect(setActionMode).toHaveBeenCalledWith('agent');
    expect(sync.ensureSearchServicesLoaded).not.toHaveBeenCalled();
  });
});
