/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { EgressProxyConfig } from '../EgressProxyConfig';
import * as llmConfig from '@/services/llm-config';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/llm-config', () => ({
  testProxyConnection: vi.fn(),
}));

describe('EgressProxyConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders proxy input with current value', () => {
    const handleChange = vi.fn();
    render(
      <EgressProxyConfig
        value="http://127.0.0.1:7890"
        onChange={handleChange}
      />,
    );

    const input = screen.getByPlaceholderText('egressProxyPlaceholder') as HTMLInputElement;
    expect(input).toBeInTheDocument();
    expect(input.value).toBe('http://127.0.0.1:7890');
  });

  it('triggers onChange when user modifies input', () => {
    const handleChange = vi.fn();
    render(
      <EgressProxyConfig
        value=""
        onChange={handleChange}
      />,
    );

    const input = screen.getByPlaceholderText('egressProxyPlaceholder');
    fireEvent.change(input, { target: { value: 'socks5://127.0.0.1:1080' } });
    expect(handleChange).toHaveBeenCalledWith('socks5://127.0.0.1:1080');
  });

  it('tests proxy connectivity successfully and displays latency', async () => {
    vi.mocked(llmConfig.testProxyConnection).mockResolvedValueOnce({
      success: true,
      latency_ms: 120,
      error: null,
    });

    render(
      <EgressProxyConfig
        value="http://127.0.0.1:7890"
        onChange={vi.fn()}
      />,
    );

    const button = screen.getByText('testProxy');
    fireEvent.click(button);

    await waitFor(() => {
      expect(llmConfig.testProxyConnection).toHaveBeenCalledWith('http://127.0.0.1:7890', undefined);
      expect(screen.getByText(/proxyConnected/)).toBeInTheDocument();
      expect(screen.getByText(/120ms/)).toBeInTheDocument();
    });
  });

  it('displays error message when proxy test fails', async () => {
    vi.mocked(llmConfig.testProxyConnection).mockResolvedValueOnce({
      success: false,
      latency_ms: null,
      error: 'Connection refused',
    });

    render(
      <EgressProxyConfig
        value="http://127.0.0.1:9999"
        onChange={vi.fn()}
      />,
    );

    const button = screen.getByText('testProxy');
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText(/proxyFailed: Connection refused/)).toBeInTheDocument();
    });
  });

  it('forwards targetUrl to testProxyConnection when provided', async () => {
    vi.mocked(llmConfig.testProxyConnection).mockResolvedValueOnce({
      success: true,
      latency_ms: 85,
      error: null,
    });

    render(
      <EgressProxyConfig
        value="http://127.0.0.1:7890"
        onChange={vi.fn()}
        targetUrl="https://api.openai.com/v1"
      />,
    );

    const button = screen.getByText('testProxy');
    fireEvent.click(button);

    await waitFor(() => {
      expect(llmConfig.testProxyConnection).toHaveBeenCalledWith(
        'http://127.0.0.1:7890',
        'https://api.openai.com/v1',
      );
    });
  });
});
