/** @vitest-environment jsdom */
/**
 * [INPUT]
 * - @/components/features/settings/sections/system/SystemSection (real, with the real useSystemConfig)
 * - @/components/features/settings/sections/system/SandboxResetCard (real, with the real ConfirmDialog)
 * - locales/{en,zh,zh-TW,ja,ko,de}.json (real copy)
 * - @/lib/api: apiRequest, ApiError
 *
 * [OUTPUT]
 * - Test suite for the cloud (sandbox) build of the System settings tab
 *
 * [POS]
 * The only suite that renders the cloud System tab end to end: the page gate, the real confirmation dialog and
 * every shipped locale's copy. A missing translation key, a broken ICU string or a card that never leaves the
 * loading skeleton fails here, which the card suite (identity translator, stubbed dialog) cannot see.
 */

import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SystemSection from '../SystemSection';
import { ApiError, apiRequest } from '@/lib/api';
import { toast } from '@/lib/utils/toast';
import de from '../../../../../../../locales/de.json';
import en from '../../../../../../../locales/en.json';
import ja from '../../../../../../../locales/ja.json';
import ko from '../../../../../../../locales/ko.json';
import zhTW from '../../../../../../../locales/zh-TW.json';
import zh from '../../../../../../../locales/zh.json';

// The global setup stubs next-intl with an identity translator; this suite asserts the real locale copy.
vi.mock('next-intl', async (importOriginal) => importOriginal<typeof import('next-intl')>());

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: vi.fn(),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock('@/lib/deploy-mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/deploy-mode')>()),
  isLocalMode: () => false,
  isTauriRuntime: () => false,
}));

vi.mock('@/hooks/ui/useDirtyGuard', () => ({ useDirtyGuard: vi.fn() }));
vi.mock('@/hooks/billing/useIngressRequirement', () => ({ useIngressRequirement: () => null }));
vi.mock('@/hooks/tauri/useTauri', () => ({ useTauri: () => ({ isTauri: false, invoke: vi.fn() }) }));
vi.mock('@/services/webui-auth', () => ({
  fetchWebuiProtection: vi.fn().mockResolvedValue({ require_password: false }),
  updateWebuiProtection: vi.fn(),
}));

// Cards the cloud tab never renders; stubbed only to keep their heavy import graphs out of jsdom.
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
vi.mock('../DomainSkillsCard', stubCard);
vi.mock('../SavedSessionsCard', stubCard);
vi.mock('../PushNotificationCard', stubCard);
vi.mock('../AgentCommerceBudgetSection', stubCard);
vi.mock('../../knowledge/MemoryMonitorCard', stubCard);
vi.mock('../AccessCard', () => ({ AccessCard: () => null }));
vi.mock('@/components/features/health/DoctorDashboard', () => ({ DoctorDashboard: () => null }));

const LOCALES = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;
type LocaleCode = keyof typeof LOCALES;

const renderCloudSystemTab = (locale: LocaleCode) =>
  render(
    <NextIntlClientProvider locale={locale} messages={{ settings: { system: LOCALES[locale].settings.system } }}>
      <SystemSection />
    </NextIntlClientProvider>,
  );

describe.each(Object.keys(LOCALES) as LocaleCode[])('cloud System tab (%s)', (locale) => {
  const copy = LOCALES[locale].settings.system.sandboxReset;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('leaves the loading skeleton and shows the reset card, and nothing from the local tab', async () => {
    renderCloudSystemTab(locale);

    expect(await screen.findByText(copy.title)).toBeInTheDocument();
    expect(screen.getAllByText(copy.title)).toHaveLength(1);
    expect(screen.getByText(copy.description)).toBeInTheDocument();
    expect(screen.getByText(copy.preserved)).toBeInTheDocument();
    expect(screen.getByText(copy.reset)).toBeInTheDocument();
    expect(screen.queryByText(LOCALES[locale].settings.system.title)).not.toBeInTheDocument();
  });

  it('asks before doing anything, and Cancel sends nothing', async () => {
    renderCloudSystemTab(locale);
    fireEvent.click(await screen.findByRole('button', { name: copy.button }));

    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText(copy.confirmTitle)).toBeInTheDocument();
    expect(within(dialog).getByText(copy.confirmDescription)).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: copy.cancel }));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('confirming sends one reset request and reports it in the user language', async () => {
    vi.mocked(apiRequest).mockResolvedValue({ status: 'accepted' });
    renderCloudSystemTab(locale);
    fireEvent.click(await screen.findByRole('button', { name: copy.button }));

    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: copy.confirm }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(copy.success));
    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(apiRequest).toHaveBeenCalledWith('/system/sandbox/recreate', {
      method: 'POST',
      body: JSON.stringify({ reset_python_env: true }),
      silent: true,
    });
    expect(toast.error).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  });

  it.each([
    ['the control plane failed', 502, copy.failed],
    ['tasks are still running', 409, copy.busy],
  ])('reports in the user language when %s', async (_reason, status, message) => {
    vi.mocked(apiRequest).mockRejectedValue(new ApiError('server-side English text', status));
    renderCloudSystemTab(locale);
    fireEvent.click(await screen.findByRole('button', { name: copy.button }));

    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: copy.confirm }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(message));
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.success).not.toHaveBeenCalled();
  });
});
