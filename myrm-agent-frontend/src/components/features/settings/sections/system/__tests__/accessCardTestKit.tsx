import type { ReactNode } from 'react';
import { vi } from 'vitest';

import type { TunnelStatus } from '@/services/remoteAccess';
import type { IngressRequirementSnapshot } from '@/services/system';
import { DEFAULT_SYSTEM_CONFIG, type SystemConfig } from '@/types/system';

/**
 * Shared doubles and fixtures for the AccessCard suites.
 *
 * `vi.mock` registrations stay in each test file (they are hoisted per file) and hand back the
 * `*Mock` module objects below through an async factory, so a suite and its mocks share one set of `vi.fn`s.
 * Rendering stays in the suites too: this kit must not import the component under test, or the
 * factories would re-enter it while it is still loading.
 */

export const PORT = 8080;
export const INGRESS_URL = 'https://ingress.example.com';
export const STOPPED: TunnelStatus = { state: 'stopped', publicUrl: '', error: '', provider: 'cloudflared' };
export const RUNNING: TunnelStatus = {
  state: 'running',
  publicUrl: 'https://tunnel.example.com',
  error: '',
  provider: 'cloudflared',
};

export const requirement = (required: boolean): IngressRequirementSnapshot => ({
  required,
  has_public_ingress: false,
  reasons: [],
  channels: {},
});

export const doubles = {
  locale: 'en',
  config: { publicIngressBaseUrl: '', setPublicIngressBaseUrl: vi.fn() },
  pwa: { isInstallable: false, isInstalled: false, promptInstall: vi.fn() },
  isLocalMode: vi.fn<() => boolean>(),
  isTauriRuntime: vi.fn<() => boolean>(),
  getLocalNetwork: vi.fn(),
  getIngressUrl: vi.fn(),
  testIngressHealth: vi.fn(),
  fetchWebuiProtection: vi.fn(),
  getTunnelStatus: vi.fn(),
  startTunnel: vi.fn(),
  stopTunnel: vi.fn(),
  createPairingToken: vi.fn(),
  getE2EEPublicKey: vi.fn(),
  writeToClipboard: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
};

const stableT = Object.assign((key: string) => key, { has: () => true });

export const nextIntlMock = { useTranslations: () => stableT, useLocale: () => doubles.locale };
export const deployModeOverrides = {
  getDocsUrl: (path: string, locale: string) => `https://docs.example.com${locale === 'zh' ? '/zh' : ''}${path}`,
  isLocalMode: () => doubles.isLocalMode(),
  isTauriRuntime: () => doubles.isTauriRuntime(),
};
export const entitlementGateMock = { default: ({ children }: { children: ReactNode }) => <>{children}</> };
export const tailscaleCardMock = { TailscaleAccessCard: () => null };
export const configStoreMock = {
  default: <T,>(select: (state: typeof doubles.config) => T) => select(doubles.config),
};
export const pwaInstallMock = { usePWAInstall: () => doubles.pwa };
export const systemServiceMock = {
  systemService: {
    getLocalNetwork: doubles.getLocalNetwork,
    getIngressUrl: doubles.getIngressUrl,
    testIngressHealth: doubles.testIngressHealth,
  },
};
export const webuiAuthMock = { fetchWebuiProtection: doubles.fetchWebuiProtection };
export const remoteAccessMock = {
  remoteAccessService: {
    getTunnelStatus: doubles.getTunnelStatus,
    startTunnel: doubles.startTunnel,
    stopTunnel: doubles.stopTunnel,
    createPairingToken: doubles.createPairingToken,
    getE2EEPublicKey: doubles.getE2EEPublicKey,
  },
};
export const clipboardMock = { writeToClipboard: doubles.writeToClipboard };
export const toastMock = { toast: { success: doubles.toastSuccess, error: doubles.toastError } };
export const fingerprintMock = { computeE2EEFingerprintFromB64: (key: string) => `fingerprint:${key}` };

/** Desktop shell, local mode, password required, tunnel stopped, nothing configured. */
export function resetDoubles() {
  vi.clearAllMocks();
  doubles.locale = 'en';
  doubles.config.publicIngressBaseUrl = '';
  doubles.pwa.isInstallable = false;
  doubles.pwa.isInstalled = false;
  doubles.isLocalMode.mockReturnValue(true);
  doubles.isTauriRuntime.mockReturnValue(true);
  doubles.getLocalNetwork.mockResolvedValue({ ip: '', url: '', hint: '' });
  doubles.getIngressUrl.mockResolvedValue('');
  doubles.testIngressHealth.mockResolvedValue(true);
  doubles.fetchWebuiProtection.mockResolvedValue({ require_password: true });
  doubles.getTunnelStatus.mockResolvedValue(STOPPED);
  doubles.startTunnel.mockResolvedValue(RUNNING);
  doubles.stopTunnel.mockResolvedValue(STOPPED);
  doubles.createPairingToken.mockResolvedValue({ token: 'pairing-token', mobilePath: '/m/pair' });
  doubles.getE2EEPublicKey.mockResolvedValue({ publicKeyB64: 'SERVER_KEY' });
}

export interface CardOptions {
  config?: Partial<SystemConfig>;
  ingress?: IngressRequirementSnapshot | null;
  localIP?: string;
}

export function cardProps({ config, ingress, localIP }: CardOptions = {}) {
  return {
    config: { ...DEFAULT_SYSTEM_CONFIG, enableWebUIMode: true, webuiPort: PORT, ...config } satisfies SystemConfig,
    localIP: localIP ?? '192.168.1.8',
    ingressSnapshot: ingress === undefined ? requirement(false) : ingress,
  };
}
