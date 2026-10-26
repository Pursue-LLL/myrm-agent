/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { confirmAction } from '@/lib/app-dialog';
import { toast } from '@/lib/utils/toast';
import DomainSkillsCard from '../DomainSkillsCard';

const stableT = (key: string, values?: { name?: string }) => (values?.name ? `${key}:${values.name}` : key);
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('@/lib/app-dialog', () => ({ confirmAction: vi.fn() }));
vi.mock('@/lib/utils/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/utils/apiConfig', () => ({ getBackendUrl: () => 'http://api.test' }));
vi.mock('@/lib/utils/authHeaders', () => ({ getAuthHeaders: () => ({}) }));

const skills = [
  { id: 'skill-1', name: 'Shop helper', domains: ['shop.example'], python_tools: {}, is_builtin: false },
  { id: 'skill-2', name: 'Built-in helper', domains: ['docs.example'], python_tools: {}, is_builtin: true },
];

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

describe('DomainSkillsCard delete', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      init?.method === 'DELETE' ? { ok: true } : { ok: true, json: async () => skills },
    );
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('removes the skill after the user confirms, naming it in the question', async () => {
    vi.mocked(confirmAction).mockResolvedValue(true);
    render(<DomainSkillsCard />);

    fireEvent.click(await screen.findByTitle('delete'));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        'http://api.test/api/v1/browser/domain-skills/skill-1',
        expect.objectContaining({ method: 'DELETE' }),
      ),
    );
    expect(confirmAction).toHaveBeenCalledExactlyOnceWith({
      variant: 'destructive',
      description: 'confirmDelete:Shop helper',
      confirmText: 'delete',
    });
    await waitFor(() => expect(screen.queryByText('Shop helper')).toBeNull());
    expect(toast.success).toHaveBeenCalledWith('deleteSuccess:Shop helper');
  });

  it('keeps the skill, and sends nothing, when the user declines', async () => {
    vi.mocked(confirmAction).mockResolvedValue(false);
    render(<DomainSkillsCard />);

    fireEvent.click(await screen.findByTitle('delete'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(1));
    await settle();

    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'DELETE')).toHaveLength(0);
    expect(screen.getByText('Shop helper')).toBeInTheDocument();
  });

  it('offers deletion only for skills the user added', async () => {
    render(<DomainSkillsCard />);

    await screen.findByText('Built-in helper');

    expect(screen.getAllByTitle('delete')).toHaveLength(1);
  });
});
