/** @vitest-environment jsdom */
'use client';

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { mockApiRequest } = vi.hoisted(() => ({
  mockApiRequest: vi.fn(),
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => mockApiRequest(...args),
}));

import { AgentTrustedDesktopApps } from '../AgentTrustedDesktopApps';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('AgentTrustedDesktopApps', () => {
  it('adds a typed app name', async () => {
    mockApiRequest.mockResolvedValue({ apps: [] });
    const onChange = vi.fn();
    render(<AgentTrustedDesktopApps apps={[]} onChange={onChange} />);
    const input = screen.getByPlaceholderText('trustedDesktopAppsPlaceholder');
    fireEvent.change(input, { target: { value: 'SAP GUI' } });
    fireEvent.click(screen.getByText('trustedDesktopAppsAdd'));
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith([{ name: 'SAP GUI' }]);
    });
  });

  it('attaches app_id when the name matches a trusted suggestion', async () => {
    mockApiRequest.mockResolvedValue({
      apps: [{ trust_key: 'com.sap.gui', display_name: 'SAP GUI', app_id: 'com.sap.gui' }],
    });
    const onChange = vi.fn();
    render(<AgentTrustedDesktopApps apps={[]} onChange={onChange} />);
    await waitFor(() => {
      expect(mockApiRequest).toHaveBeenCalled();
    });
    const input = screen.getByPlaceholderText('trustedDesktopAppsPlaceholder');
    fireEvent.change(input, { target: { value: 'SAP GUI' } });
    fireEvent.click(screen.getByText('trustedDesktopAppsAdd'));
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith([{ name: 'SAP GUI', app_id: 'com.sap.gui' }]);
    });
  });

  it('removes an app', () => {
    mockApiRequest.mockResolvedValue({ apps: [] });
    const onChange = vi.fn();
    render(
      <AgentTrustedDesktopApps apps={[{ name: 'SAP GUI' }]} onChange={onChange} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'trustedDesktopAppsRemove' }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it('is read-only when readonly', () => {
    mockApiRequest.mockResolvedValue({ apps: [] });
    render(
      <AgentTrustedDesktopApps apps={[{ name: 'SAP GUI' }]} onChange={vi.fn()} readonly />,
    );
    expect(screen.queryByPlaceholderText('trustedDesktopAppsPlaceholder')).toBeNull();
  });
});
