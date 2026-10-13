/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import type { MCPServiceConfig } from '@/store/config/types';
import {
  GATE_ALLOWED,
  makeStoredConfig,
  mockGateMcpEnable,
  mockSetMCPConfigs,
  mockToast,
  resetConnectDialogMocks,
  restoreConnectDialogGlobals,
} from './connectDialogTestKit';

vi.mock('next-intl', async () => (await import('./connectDialogTestKit')).nextIntlMock);
vi.mock('@/hooks/shared/useToast', async () => (await import('./connectDialogTestKit')).toastMock);
vi.mock('@/hooks/settings/useMcpSecurityGate', async () => (await import('./connectDialogTestKit')).securityGateMock);
vi.mock('@/lib/utils/mcp-config', async () => (await import('./connectDialogTestKit')).mcpConfigUtilsMock);

import { useCatalogSecurityGate } from '../useCatalogSecurityGate';

describe('useCatalogSecurityGate', () => {
  beforeEach(resetConnectDialogMocks);
  afterEach(restoreConnectDialogGlobals);

  it('does not store a second copy of a service that was added while the acknowledgement was open', async () => {
    mockGateMcpEnable.mockResolvedValueOnce({ ...GATE_ALLOWED, needsAcknowledgement: true, allowed: false });
    const onConnected = vi.fn();
    const { result, rerender } = renderHook(
      ({ mcpConfigs }: { mcpConfigs: MCPServiceConfig[] }) =>
        useCatalogSecurityGate({
          entryName: 'Svc',
          catalogMcpConfig: null,
          mcpConfigs,
          setMCPConfigs: mockSetMCPConfigs,
          onConnected,
        }),
      { initialProps: { mcpConfigs: [] as MCPServiceConfig[] } },
    );

    await act(async () => {
      await result.current.runCatalogSecurityGate(makeStoredConfig('svc'));
    });
    expect(result.current.pendingAck).not.toBeNull();

    rerender({ mcpConfigs: [makeStoredConfig('svc')] });
    await act(async () => {
      await result.current.confirmAcknowledgement();
    });

    expect(mockSetMCPConfigs).not.toHaveBeenCalled();
    expect(mockToast).toHaveBeenCalledExactlyOnceWith({ title: 'connectSuccess' });
    expect(onConnected).toHaveBeenCalledTimes(1);
  });
});
