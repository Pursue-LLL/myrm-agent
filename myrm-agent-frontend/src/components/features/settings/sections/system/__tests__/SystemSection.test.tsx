/** @vitest-environment jsdom */
/**
 * [INPUT]
 * - @/components/features/settings/sections/system/SystemSection
 * - @/hooks/settings/useSystemConfig
 * - @/hooks/tauri/useTauri
 *
 * [OUTPUT]
 * - Page-level test suite for the system settings panel
 *
 * [POS]
 * Renders the real panel with the real LockedUseCard / PrivacyCurtainCard and every unrelated card
 * stubbed, so it pins the staged-vs-saved binding that card-level tests cannot see: a toggle must flip
 * on click (staged value), mark the page dirty and persist through the page-level save.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DEFAULT_SYSTEM_CONFIG } from '@/types/system';
import SystemSection from '../SystemSection';

const mocks = vi.hoisted(() => {
  const savedConfig = {
    enableWebUIMode: false,
    enableRemoteAccess: false,
    webuiPort: 3000,
    apiPort: 25808,
    requirePassword: true,
    closeToTray: true,
    autoLaunchAtLogin: true,
    configVersion: 1,
    globalShortcut: 'Option+Space',
    appshotShortcut: 'CommandOrControl+Shift+A',
    appshotExcludedApps: [] as string[],
    lockedUseEnabled: false,
    privacyCurtainEnabled: false,
    voicePttShortcut: 'CommandOrControl+Shift+V',
    idleReclaimTimeoutSeconds: 1800,
  };
  return {
    savedConfig,
    systemConfig: {
      config: savedConfig,
      currentMode: 'desktop' as const,
      localIP: '',
      loading: false,
      saveConfig: vi.fn(),
      saveAndRestart: vi.fn(),
    },
    invoke: vi.fn(),
    updateWebuiProtection: vi.fn(),
  };
});

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: () => true,
  isTauriRuntime: () => false,
}));

vi.mock('@/hooks/settings/useSystemConfig', () => ({
  useSystemConfig: () => mocks.systemConfig,
}));

vi.mock('@/hooks/ui/useDirtyGuard', () => ({
  useDirtyGuard: vi.fn(),
}));

vi.mock('@/hooks/billing/useIngressRequirement', () => ({
  useIngressRequirement: () => null,
}));

vi.mock('@/hooks/tauri/useTauri', () => ({
  useTauri: () => ({ isTauri: true, invoke: mocks.invoke }),
}));

vi.mock('@/services/webui-auth', () => ({
  fetchWebuiProtection: vi.fn().mockResolvedValue({ require_password: true }),
  updateWebuiProtection: (...args: unknown[]) => mocks.updateWebuiProtection(...args),
}));

const stubCard = vi.hoisted(() => () => ({ default: () => null }));
vi.mock('../BrowserPoolCard', stubCard);
vi.mock('../BrowserDoctorCard', stubCard);
vi.mock('../BrowserProxyCard', stubCard);
vi.mock('../CaptchaSolverCard', stubCard);
vi.mock('../CloudBrowserCard', stubCard);
vi.mock('../DesktopPermissionsCard', stubCard);
vi.mock('../WebuiAccessSecurityPanel', stubCard);
vi.mock('../ServerConnectionCard', stubCard);
vi.mock('../StorageCard', stubCard);
vi.mock('../SandboxResetCard', stubCard);
vi.mock('../DomainSkillsCard', stubCard);
vi.mock('../SavedSessionsCard', stubCard);
vi.mock('../PushNotificationCard', stubCard);
vi.mock('../AgentCommerceBudgetSection', stubCard);
vi.mock('../../knowledge/MemoryMonitorCard', stubCard);
vi.mock('../AccessCard', () => ({ AccessCard: () => null }));
vi.mock('@/components/features/health/DoctorDashboard', () => ({ DoctorDashboard: () => null }));

describe('SystemSection staged toggles', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.systemConfig.config = { ...mocks.savedConfig };
    mocks.systemConfig.saveConfig.mockResolvedValue(undefined);
    mocks.updateWebuiProtection.mockResolvedValue(undefined);
    mocks.invoke.mockImplementation((cmd: string) => {
      if (cmd === 'screen_lock_platform_support') {
        return Promise.resolve({
          detection: true,
          unlock: true,
          keychain: true,
          curtain_supported: true,
          curtain_capture_excluded_on_desktop: true,
          curtain_capture_exclusion_ready: true,
          platform: 'macos',
        });
      }
      return Promise.resolve(false);
    });
  });

  it('keeps the page-level defaults aligned with the saved fixture', () => {
    expect(mocks.savedConfig.lockedUseEnabled).toBe(DEFAULT_SYSTEM_CONFIG.lockedUseEnabled);
    expect(mocks.savedConfig.privacyCurtainEnabled).toBe(DEFAULT_SYSTEM_CONFIG.privacyCurtainEnabled);
  });

  it('flips the locked-use switch on click and enables the page save', async () => {
    render(<SystemSection />);

    const toggle = await screen.findByRole('switch', { name: 'layer2Title' });
    await waitFor(() => expect(toggle).toBeEnabled());
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('button', { name: 'save' })).toBeDisabled();

    fireEvent.click(toggle);

    expect(screen.getByRole('switch', { name: 'layer2Title' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('button', { name: 'save' })).toBeEnabled();
  });

  it('persists the staged locked-use value through the page-level save', async () => {
    render(<SystemSection />);

    const toggle = await screen.findByRole('switch', { name: 'layer2Title' });
    await waitFor(() => expect(toggle).toBeEnabled());
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole('button', { name: 'save' }));

    await waitFor(() =>
      expect(mocks.systemConfig.saveConfig).toHaveBeenCalledWith(expect.objectContaining({ lockedUseEnabled: true })),
    );
  });

  it('flips the privacy-curtain switch on click and persists it through the page-level save', async () => {
    render(<SystemSection />);

    const toggle = await screen.findByRole('switch', { name: 'autoTitle' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');

    fireEvent.click(toggle);

    expect(screen.getByRole('switch', { name: 'autoTitle' })).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'save' }));
    await waitFor(() =>
      expect(mocks.systemConfig.saveConfig).toHaveBeenCalledWith(
        expect.objectContaining({ privacyCurtainEnabled: true }),
      ),
    );
  });
});
