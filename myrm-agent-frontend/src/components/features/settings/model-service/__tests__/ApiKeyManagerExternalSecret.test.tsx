/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import ApiKeyManager from '../ApiKeyManager';
import * as llmConfig from '@/services/llm-config';
import { TooltipProvider } from '@/components/primitives/tooltip';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params) {
    let str = key;
    for (const [k, v] of Object.entries(params)) {
      str += `:${k}=${v}`;
    }
    return str;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockToast = vi.fn();
vi.mock('@/hooks/shared/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
  toast: (...args: unknown[]) => mockToast(...args),
}));

vi.mock('@/services/llm-config', () => ({
  validateExternalSecretReference: vi.fn(),
  fetchCredentialPoolStats: vi.fn().mockResolvedValue([]),
  resetCredentialPoolCooldowns: vi.fn().mockResolvedValue({ reset_count: 0 }),
}));

describe('ApiKeyManager External Secret Source Support', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders test button for external secret reference (op://)', async () => {
    const apiKeys = [
      {
        id: 'key-1',
        key: 'op://Personal/OpenAI/credential',
        isActive: true,
        createdAt: 1000,
      },
    ];

    render(
      <TooltipProvider>
        <ApiKeyManager apiKeys={apiKeys} onChange={vi.fn()} />
      </TooltipProvider>,
    );

    const testBtn = screen.getByText('validateExternalKey');
    expect(testBtn).toBeDefined();

    vi.mocked(llmConfig.validateExternalSecretReference).mockResolvedValueOnce({
      valid: true,
      masked_preview: 'sk-...999',
    });

    fireEvent.click(testBtn);

    await waitFor(() => {
      expect(llmConfig.validateExternalSecretReference).toHaveBeenCalledWith('op://Personal/OpenAI/credential');
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: expect.stringContaining('externalSecretValid:preview=sk-...999'),
        }),
      );
    });
  });

  it('does not render test button for regular plain API key', () => {
    const apiKeys = [
      {
        id: 'key-2',
        key: 'sk-normal-api-key-value',
        isActive: true,
        createdAt: 1000,
      },
    ];

    render(
      <TooltipProvider>
        <ApiKeyManager apiKeys={apiKeys} onChange={vi.fn()} />
      </TooltipProvider>,
    );
    expect(screen.queryByText('validateExternalKey')).toBeNull();
  });
});
