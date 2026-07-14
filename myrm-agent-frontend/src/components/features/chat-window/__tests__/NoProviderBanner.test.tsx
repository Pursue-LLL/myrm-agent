'use client';

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/',
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('lucide-react', () => ({
  AlertCircle: (props: Record<string, unknown>) => <svg data-testid="alert-icon" {...props} />,
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, onClick, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button onClick={onClick} {...props}>
      {children}
    </button>
  ),
}));

const mockUseProviderStore = vi.fn();
vi.mock('@/store/useProviderStore', () => ({
  default: (selector: (s: unknown) => unknown) => mockUseProviderStore(selector),
}));

import NoProviderBanner from '../NoProviderBanner';

describe('NoProviderBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when store is not initialized', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = { isInitialized: false, providers: [] };
      return selector(state);
    });

    const { container } = render(<NoProviderBanner />);
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when a provider is enabled with active API key', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [
          { id: 'openai', isEnabled: true, apiKeys: [{ isActive: true, key: 'sk-xxx' }] },
        ],
      };
      return selector(state);
    });

    const { container } = render(<NoProviderBanner />);
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when ollama provider is enabled (no API key needed)', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [{ id: 'ollama', isEnabled: true, apiKeys: [] }],
      };
      return selector(state);
    });

    const { container } = render(<NoProviderBanner />);
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when lm_studio provider is enabled', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [{ id: 'lm_studio', isEnabled: true, apiKeys: [] }],
      };
      return selector(state);
    });

    const { container } = render(<NoProviderBanner />);
    expect(container.innerHTML).toBe('');
  });

  it('renders banner when initialized but no provider is enabled', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [
          { id: 'openai', isEnabled: false, apiKeys: [] },
        ],
      };
      return selector(state);
    });

    render(<NoProviderBanner />);
    expect(screen.getByText('noProviderBanner')).toBeInTheDocument();
    expect(screen.getByText('noProviderAction')).toBeInTheDocument();
    expect(screen.getByTestId('alert-icon')).toBeInTheDocument();
  });

  it('renders banner when provider enabled but API key inactive', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [
          { id: 'openai', isEnabled: true, apiKeys: [{ isActive: false, key: 'sk-xxx' }] },
        ],
      };
      return selector(state);
    });

    render(<NoProviderBanner />);
    expect(screen.getByText('noProviderBanner')).toBeInTheDocument();
  });

  it('renders banner when provider enabled but API key empty', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [
          { id: 'openai', isEnabled: true, apiKeys: [{ isActive: true, key: '' }] },
        ],
      };
      return selector(state);
    });

    render(<NoProviderBanner />);
    expect(screen.getByText('noProviderBanner')).toBeInTheDocument();
  });

  it('navigates to /settings/models on button click', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [],
      };
      return selector(state);
    });

    render(<NoProviderBanner />);
    fireEvent.click(screen.getByText('noProviderAction'));
    expect(mockPush).toHaveBeenCalledWith('/settings/models');
  });

  it('renders banner with correct amber styling classes', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = { isInitialized: true, providers: [] };
      return selector(state);
    });

    const { container } = render(<NoProviderBanner />);
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.className).toContain('border-amber-200');
    expect(wrapper.className).toContain('bg-amber-50');
  });
});
