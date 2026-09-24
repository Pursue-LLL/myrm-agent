import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ServerConnectionCard from '../ServerConnectionCard';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: string[]) => args.filter(Boolean).join(' '),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('ServerConnectionCard runtime gating', () => {
  it('renders nothing outside Tauri so web users never see the desktop card', () => {
    const { container } = render(<ServerConnectionCard />);
    expect(container.firstChild).toBeNull();
    expect(screen.queryByText('title')).toBeNull();
  });

  it('renders the connection card inside Tauri runtime', async () => {
    vi.resetModules();
    vi.doMock('@/lib/deploy-mode', async (importOriginal) => {
      const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
      return { ...actual, isTauriRuntime: () => true };
    });
    const { default: TauriCard } = await import('../ServerConnectionCard');
    const { container } = render(<TauriCard />);
    expect(container.firstChild).not.toBeNull();
    expect(screen.getByText('title')).toBeTruthy();
    vi.doUnmock('@/lib/deploy-mode');
  });
});
