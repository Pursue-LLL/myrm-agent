import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

type Result = { models: { id: string; name: string }[]; apiError?: string; source: 'api' };
const pending: { providerId: string; resolve: (r: Result) => void }[] = [];

vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k }));
vi.mock('@/services/models-dev', () => ({
  getModelsForProvider: (providerId: string) =>
    new Promise<Result>((resolve) => pending.push({ providerId, resolve })),
  searchModels: (m: unknown[]) => m,
  mapToCustomModelInfo: () => ({}),
}));

import ModelImportDialog from '../ModelImportDialog';

const base = { providerType: 'openai-compatible' as never, apiKey: 'k', existingModels: [], onImportModels: () => {}, onOpenChange: () => {} };

describe('stale discovery', () => {
  it('provider A response arriving after reopening for provider B', async () => {
    const view = render(<ModelImportDialog {...base} open providerId="A" apiUrl="http://a" />);
    view.rerender(<ModelImportDialog {...base} open={false} providerId="A" apiUrl="http://a" />);
    view.rerender(<ModelImportDialog {...base} open providerId="B" apiUrl="http://b" />);
    expect(pending.map((p) => p.providerId)).toEqual(['A', 'B']);
    // B still loading; A's slow response lands now
    await act(async () => {
      pending[0].resolve({ models: [{ id: 'a-model', name: 'a-model' }], source: 'api' });
    });
    const shownA = screen.queryAllByText('a-model').length;
    console.log('A model visible inside provider B dialog while B still pending:', shownA > 0);
    await act(async () => {
      pending[1].resolve({ models: [{ id: 'b-model', name: 'b-model' }], source: 'api' });
    });
    console.log('after B resolves, a-model visible:', screen.queryAllByText('a-model').length > 0, 'b-model visible:', screen.queryAllByText('b-model').length > 0);
    expect(true).toBe(true);
  });
});
