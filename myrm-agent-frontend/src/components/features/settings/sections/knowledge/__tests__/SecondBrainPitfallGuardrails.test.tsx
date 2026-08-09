/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SecondBrainPitfallGuardrails from '../SecondBrainPitfallGuardrails';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({ setInputMessage: vi.fn() }),
  },
}));

vi.mock('@/lib/deploy-mode', () => ({
  getDocsUrl: (path: string = '/') => `https://docs.test${path}`,
}));

describe('SecondBrainPitfallGuardrails', () => {
  it('renders pitfall panel and team kb chips', () => {
    render(<SecondBrainPitfallGuardrails onGoToImport={vi.fn()} />);
    expect(screen.getByTestId('second-brain-pitfall-panel')).toBeTruthy();
    expect(screen.getByTestId('second-brain-troubleshooting-ladder')).toBeTruthy();
    expect(screen.getByTestId('second-brain-team-kb-opsSop')).toBeTruthy();
    expect(screen.getByTestId('second-brain-extract-taxonomy')).toBeTruthy();
  });
});
