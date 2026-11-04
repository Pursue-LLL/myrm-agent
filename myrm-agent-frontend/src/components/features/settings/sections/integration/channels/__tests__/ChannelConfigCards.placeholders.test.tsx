/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mocks = vi.hoisted(() => ({
  getMatrixCredentials: vi.fn(),
  getOneBotCredentials: vi.fn(),
}));

vi.mock('@/services/channels', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    getMatrixCredentials: (...args: unknown[]) => mocks.getMatrixCredentials(...args),
    getOneBotCredentials: (...args: unknown[]) => mocks.getOneBotCredentials(...args),
    testMatrixConnection: vi.fn().mockResolvedValue({ ok: true }),
    testOneBotConnection: vi.fn().mockResolvedValue({ ok: true }),
  };
});

import { MatrixConfigCard } from '../MatrixConfigCard';
import { OneBotConfigCard } from '../OneBotConfigCard';

describe('channel credential placeholders', () => {
  beforeEach(() => {
    mocks.getMatrixCredentials.mockReset().mockResolvedValue({
      homeserverUrl: '',
      accessToken: '',
      deviceId: '',
      userId: '',
      password: '',
      encryption: false,
      proxy: '',
    });
    mocks.getOneBotCredentials.mockReset().mockResolvedValue({ wsUrl: '', accessToken: '' });
  });

  it('gives the Matrix proxy field a localized example', async () => {
    render(<MatrixConfigCard />);

    expect(await screen.findByPlaceholderText('matrixProxyPlaceholder')).toBeInTheDocument();
  });

  it('gives the OneBot token field a localized hint', async () => {
    render(<OneBotConfigCard />);

    expect(await screen.findByPlaceholderText('onebotTokenPlaceholder')).toBeInTheDocument();
  });
});
