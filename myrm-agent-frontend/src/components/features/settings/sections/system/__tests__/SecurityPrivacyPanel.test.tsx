import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import useConfigStore from '@/store/useConfigStore';
import SecurityPrivacyPanel from '../SecurityPrivacyPanel';

const { mockFetch, mockSetLocalApiKey, secretState } = vi.hoisted(() => ({
  mockFetch: vi.fn(),
  mockSetLocalApiKey: vi.fn(),
  secretState: { value: '' },
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: mockFetch,
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/hooks/settings/usePrivacyRoutingSecret', () => ({
  usePrivacyRoutingSecret: () => [secretState.value, mockSetLocalApiKey] as const,
}));

vi.mock('../AdvancedPiiConfig', () => ({ AdvancedPiiConfig: () => null }));
vi.mock('../PrivacyRuleTester', () => ({ PrivacyRuleTester: () => null }));

const KEY_PLACEHOLDER = 'privacy.routing.localApiKeyPlaceholder';

describe('SecurityPrivacyPanel local model key', () => {
  beforeEach(() => {
    secretState.value = '';
    mockFetch.mockReset().mockResolvedValue({ json: async () => ({ success: true, latency_ms: 12 }) });
    mockSetLocalApiKey.mockReset();
    useConfigStore.setState({
      privacyEnabled: true,
      privacyRouting: { localModel: 'llama3:8b', localBaseUrl: 'http://localhost:11434/v1' },
    });
  });

  it('shows the saved key as a masked field', () => {
    secretState.value = 'sk-local';

    render(<SecurityPrivacyPanel />);

    const field = screen.getByPlaceholderText(KEY_PLACEHOLDER);
    expect(field).toHaveValue('sk-local');
    expect(field).toHaveAttribute('type', 'password');
  });

  it('saves the typed key through the secret row and never into the routing preferences', () => {
    render(<SecurityPrivacyPanel />);

    fireEvent.change(screen.getByPlaceholderText(KEY_PLACEHOLDER), { target: { value: 'sk-typed' } });

    expect(mockSetLocalApiKey).toHaveBeenCalledWith('sk-typed');
    expect(useConfigStore.getState().privacyRouting).toEqual({
      localModel: 'llama3:8b',
      localBaseUrl: 'http://localhost:11434/v1',
    });
  });

  it('clears the key by saving an empty value', () => {
    secretState.value = 'sk-local';
    render(<SecurityPrivacyPanel />);

    fireEvent.change(screen.getByPlaceholderText(KEY_PLACEHOLDER), { target: { value: '' } });

    expect(mockSetLocalApiKey).toHaveBeenCalledWith('');
  });

  it('keeps editing the other routing fields without touching the key', () => {
    secretState.value = 'sk-local';
    render(<SecurityPrivacyPanel />);

    fireEvent.change(screen.getByPlaceholderText('privacy.routing.localBaseUrlPlaceholder'), {
      target: { value: 'http://localhost:1234/v1' },
    });

    expect(useConfigStore.getState().privacyRouting.localBaseUrl).toBe('http://localhost:1234/v1');
    expect(mockSetLocalApiKey).not.toHaveBeenCalled();
  });

  it.each([
    ['the saved key', 'sk-local', 'sk-local'],
    ['no key when none is saved', '', null],
  ])('tests the connection with %s', async (_label, saved, expected) => {
    secretState.value = saved;
    render(<SecurityPrivacyPanel />);

    await userEvent.click(screen.getByRole('button', { name: /privacy.routing.testConnection/ }));

    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    const [path, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(path).toBe('/config/test-local-model');
    expect(JSON.parse(String(init.body))).toEqual({
      model: 'llama3:8b',
      base_url: 'http://localhost:11434/v1',
      api_key: expected,
    });
  });
});
