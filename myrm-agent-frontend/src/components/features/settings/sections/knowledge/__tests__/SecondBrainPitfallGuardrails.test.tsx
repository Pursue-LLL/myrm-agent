/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SecondBrainPitfallGuardrails from '../SecondBrainPitfallGuardrails';

const stableT = (key: string) => key;
let currentLocale = 'en';

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => currentLocale,
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
  getDocsUrl: (path: string, locale: string) => `https://docs.test${locale === 'zh' ? '/zh' : ''}${path}`,
}));

describe('SecondBrainPitfallGuardrails', () => {
  it('renders pitfall panel and team kb chips', () => {
    render(<SecondBrainPitfallGuardrails onGoToImport={vi.fn()} />);
    expect(screen.getByTestId('second-brain-pitfall-panel')).toBeTruthy();
    expect(screen.getByTestId('second-brain-troubleshooting-ladder')).toBeTruthy();
    expect(screen.getByTestId('second-brain-team-kb-opsSop')).toBeTruthy();
    expect(screen.getByTestId('second-brain-extract-taxonomy')).toBeTruthy();
  });

  it.each([
    ['en', 'https://docs.test/guides/wiki-knowledge-base'],
    ['zh', 'https://docs.test/zh/guides/wiki-knowledge-base'],
  ])('links the troubleshooting ladder to the wiki guide in the %s docs', (locale, href) => {
    currentLocale = locale;
    render(<SecondBrainPitfallGuardrails />);
    expect(screen.getByRole('link', { name: 'ladder.stepDocs' })).toHaveAttribute('href', href);
  });
});
