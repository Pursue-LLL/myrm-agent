/**
 * @vitest-environment jsdom
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import React from 'react';

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/',
}));

const stableT = (key: string, values?: Record<string, unknown>) => {
  if (values && values.title) {
    return `${key}:${String(values.title)}`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const mockUseProviderStore = vi.fn();
vi.mock('@/store/useProviderStore', () => ({
  default: (selector: (s: unknown) => unknown) => mockUseProviderStore(selector),
}));

import { ModelOrchestrationPlaybookChip } from '../ModelOrchestrationPlaybookChip';
import { ModelOrchestrationPlaybookDialog } from '../ModelOrchestrationPlaybookDialog';

const sessionStorageMockStore = new Map<string, string>();
const mockSessionStorage = {
  getItem: (key: string) => sessionStorageMockStore.get(key) ?? null,
  setItem: (key: string, value: string) => {
    sessionStorageMockStore.set(key, String(value));
  },
  removeItem: (key: string) => {
    sessionStorageMockStore.delete(key);
  },
  clear: () => {
    sessionStorageMockStore.clear();
  },
} as Storage;

if (typeof globalThis.sessionStorage === 'undefined') {
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    value: mockSessionStorage,
  });
}

describe('ModelOrchestrationPlaybookChip & Dialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    globalThis.sessionStorage.clear();
  });

  it('renders the chip when not dismissed', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        providers: [],
        defaultModelConfig: null,
        getEnabledModels: () => [],
        setBaseModel: vi.fn(),
        setLiteModel: vi.fn(),
        setRoutingEnabled: vi.fn(),
        setRoutingLightModel: vi.fn(),
        setRoutingReasoningModel: vi.fn(),
        setAutoMoaReasoning: vi.fn(),
      };
      return selector(state);
    });

    render(<ModelOrchestrationPlaybookChip />);
    expect(screen.getByTestId('model-orchestration-playbook-chip')).toBeDefined();
    expect(screen.getByText('chipTitle')).toBeDefined();
    expect(screen.getByText('chipBadge')).toBeDefined();
  });

  it('allows dismissing the chip and persists dismissal in sessionStorage', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        providers: [],
        defaultModelConfig: null,
        getEnabledModels: () => [],
      };
      return selector(state);
    });

    render(<ModelOrchestrationPlaybookChip />);
    const dismissBtn = screen.getByRole('button', { name: 'dismiss' });
    fireEvent.click(dismissBtn);

    expect(sessionStorage.getItem('myrm_model_playbook_chip_dismissed')).toBe('true');
  });

  it('renders dialog tabs and content when opened', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        providers: [],
        defaultModelConfig: null,
        getEnabledModels: () => [
          { providerId: 'anthropic', providerName: 'Anthropic', model: 'claude-3-5-sonnet' },
          { providerId: 'deepseek', providerName: 'DeepSeek', model: 'deepseek-chat' },
        ],
        setBaseModel: vi.fn(),
        setLiteModel: vi.fn(),
        setRoutingEnabled: vi.fn(),
        setRoutingLightModel: vi.fn(),
        setRoutingReasoningModel: vi.fn(),
        setAutoMoaReasoning: vi.fn(),
      };
      return selector(state);
    });

    render(<ModelOrchestrationPlaybookDialog open={true} onOpenChange={vi.fn()} />);
    expect(screen.getByText('title')).toBeDefined();
    expect(screen.getByText('tabRecipes')).toBeDefined();
    expect(screen.getByText('tabPrinciples')).toBeDefined();
    expect(screen.getByText('tabEconomics')).toBeDefined();
  });
});
