import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AccessCard } from '../AccessCard';
import {
  INGRESS_URL,
  PORT,
  RUNNING,
  STOPPED,
  cardProps,
  doubles,
  resetDoubles,
  type CardOptions,
} from './accessCardTestKit';

vi.mock('next-intl', async () => (await import('./accessCardTestKit')).nextIntlMock);
vi.mock(import('@/lib/deploy-mode'), async (importOriginal) => ({
  ...(await importOriginal()),
  ...(await import('./accessCardTestKit')).deployModeOverrides,
}));
vi.mock(
  '@/components/billing/IngressEntitlementGate',
  async () => (await import('./accessCardTestKit')).entitlementGateMock,
);
vi.mock('../TailscaleAccessCard', async () => (await import('./accessCardTestKit')).tailscaleCardMock);
vi.mock('@/store/useConfigStore', async () => (await import('./accessCardTestKit')).configStoreMock);
vi.mock('@/hooks/pwa/usePWAInstall', async () => (await import('./accessCardTestKit')).pwaInstallMock);
vi.mock('@/services/system', async () => (await import('./accessCardTestKit')).systemServiceMock);
vi.mock('@/services/webui-auth', async () => (await import('./accessCardTestKit')).webuiAuthMock);
vi.mock('@/services/remoteAccess', async () => (await import('./accessCardTestKit')).remoteAccessMock);
vi.mock('@/lib/utils/clipboardUtils', async () => (await import('./accessCardTestKit')).clipboardMock);
vi.mock('@/lib/utils/toast', async () => (await import('./accessCardTestKit')).toastMock);
vi.mock('@/lib/e2ee/fingerprint', async () => (await import('./accessCardTestKit')).fingerprintMock);

const renderCard = (options?: CardOptions) => render(<AccessCard {...cardProps(options)} />);
const buttonOf = (label: string) => screen.getByText(label).closest('button');

describe('AccessCard public ingress', () => {
  beforeEach(resetDoubles);

  describe('card', () => {
    it('links the tunnel guide in a new tab', () => {
      renderCard();
      const link = screen.getByText('access.ingress.docsLink');
      expect(link).toHaveAttribute('href', 'https://docs.example.com/guides/tunnel');
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it.each([
      ['zh-CN', 'access.tunnel.cnHint', 'access.tunnel.globalHint'],
      ['en', 'access.tunnel.globalHint', 'access.tunnel.cnHint'],
    ])('words the tunnel hint for the %s locale', (locale, shown, hidden) => {
      doubles.locale = locale;
      renderCard();
      expect(screen.getByText(shown)).toBeInTheDocument();
      expect(screen.queryByText(hidden)).not.toBeInTheDocument();
    });

    it('shows and edits the saved ingress address', () => {
      doubles.config.publicIngressBaseUrl = INGRESS_URL;
      renderCard();
      const input = screen.getByPlaceholderText('https://...');
      expect(input).toHaveValue(INGRESS_URL);
      fireEvent.change(input, { target: { value: 'https://other.example.com' } });
      expect(doubles.config.setPublicIngressBaseUrl).toHaveBeenCalledWith('https://other.example.com');
    });
  });

  describe('password gate', () => {
    it('disables tunnel actions and says why when the desktop shell has no password', () => {
      renderCard({ config: { requirePassword: false } });
      expect(screen.getByText('access.ingress.passwordRequired')).toBeInTheDocument();
      expect(buttonOf('access.tunnel.start')).toBeDisabled();
      expect(buttonOf('access.tunnel.shareMobile')).toBeDisabled();
      expect(doubles.fetchWebuiProtection).not.toHaveBeenCalled();
    });

    it('trusts the server over the stored setting in the browser', async () => {
      doubles.isTauriRuntime.mockReturnValue(false);
      renderCard({ config: { requirePassword: false } });
      await waitFor(() => expect(buttonOf('access.tunnel.start')).toBeEnabled());
      expect(screen.queryByText('access.ingress.passwordRequired')).not.toBeInTheDocument();
    });

    it('keeps the stored setting when the server cannot answer', async () => {
      doubles.isTauriRuntime.mockReturnValue(false);
      doubles.fetchWebuiProtection.mockRejectedValue(new Error('offline'));
      renderCard({ config: { requirePassword: false } });
      await waitFor(() => expect(doubles.fetchWebuiProtection).toHaveBeenCalledTimes(1));
      expect(screen.getByText('access.ingress.passwordRequired')).toBeInTheDocument();
      expect(buttonOf('access.tunnel.start')).toBeDisabled();
    });
  });

  describe('tunnel', () => {
    it('starts on the web port and remembers the public URL', async () => {
      renderCard();
      fireEvent.click(await screen.findByText('access.tunnel.start'));
      await waitFor(() => expect(doubles.startTunnel).toHaveBeenCalledWith(PORT));
      expect(await screen.findByText('access.tunnel.stop')).toBeInTheDocument();
      expect(screen.getByText(RUNNING.publicUrl)).toBeInTheDocument();
      expect(doubles.config.setPublicIngressBaseUrl).toHaveBeenCalledWith(RUNNING.publicUrl);
    });

    it('stops a running tunnel', async () => {
      doubles.getTunnelStatus.mockResolvedValue(RUNNING);
      renderCard();
      fireEvent.click(await screen.findByText('access.tunnel.stop'));
      expect(await screen.findByText('access.tunnel.start')).toBeInTheDocument();
      expect(doubles.stopTunnel).toHaveBeenCalledTimes(1);
      expect(doubles.startTunnel).not.toHaveBeenCalled();
    });

    it('surfaces the error the server reports', async () => {
      doubles.startTunnel.mockResolvedValue({ ...STOPPED, state: 'error', error: 'port in use' });
      renderCard();
      fireEvent.click(await screen.findByText('access.tunnel.start'));
      await waitFor(() => expect(doubles.toastError).toHaveBeenCalledWith('port in use'));
    });

    it('reports a failed request and frees the button again', async () => {
      doubles.startTunnel.mockRejectedValue(new Error('network'));
      renderCard();
      fireEvent.click(await screen.findByText('access.tunnel.start'));
      await waitFor(() => expect(doubles.toastError).toHaveBeenCalledWith('access.tunnel.error'));
      await waitFor(() => expect(buttonOf('access.tunnel.start')).toBeEnabled());
    });

    it('lists the end-to-end encryption details of a running tunnel', async () => {
      doubles.getTunnelStatus.mockResolvedValue(RUNNING);
      renderCard();
      expect(await screen.findByText('access.tunnel.e2eeBadge')).toBeInTheDocument();
      expect(await screen.findByText('fingerprint:SERVER_KEY')).toBeInTheDocument();
      expect(screen.getByText('NaCl Box (Curve25519)')).toBeInTheDocument();
    });
  });

  describe('mobile hub link', () => {
    async function shareHubLink() {
      doubles.config.publicIngressBaseUrl = INGRESS_URL;
      renderCard();
      fireEvent.click(await screen.findByText('access.tunnel.shareMobile'));
      await screen.findByAltText('access.tunnel.hubQrAlt');
    }

    it('is issued on its own once a password-protected tunnel runs', async () => {
      doubles.getTunnelStatus.mockResolvedValue(RUNNING);
      renderCard();
      const qr = await screen.findByAltText('access.tunnel.hubQrAlt');
      const hubUrl = `${RUNNING.publicUrl}/m/pair#e2ee=SERVER_KEY`;
      expect(qr).toHaveAttribute('src', `/webui/qrcode.png?url=${encodeURIComponent(hubUrl)}`);
      expect(doubles.createPairingToken).toHaveBeenCalledTimes(1);
    });

    it('is not issued on its own when no password protects the tunnel', async () => {
      doubles.getTunnelStatus.mockResolvedValue(RUNNING);
      renderCard({ config: { requirePassword: false } });
      await screen.findByText(RUNNING.publicUrl);
      expect(doubles.createPairingToken).not.toHaveBeenCalled();
      expect(screen.queryByAltText('access.tunnel.hubQrAlt')).not.toBeInTheDocument();
    });

    it('is copied on the saved ingress address while no tunnel runs', async () => {
      await shareHubLink();
      const hubUrl = `${INGRESS_URL}/m/pair`;
      expect(doubles.writeToClipboard).toHaveBeenCalledWith(hubUrl);
      expect(doubles.toastSuccess).toHaveBeenCalledWith('access.tunnel.shareCopied');
      expect(doubles.getE2EEPublicKey).not.toHaveBeenCalled();
      expect(screen.getByAltText('access.tunnel.hubQrAlt')).toHaveAttribute(
        'src',
        `/webui/qrcode.png?url=${encodeURIComponent(hubUrl)}`,
      );
      expect(screen.getByText('access.tunnel.hubScanHint')).toBeInTheDocument();
    });

    it('reports a failed pairing request', async () => {
      doubles.createPairingToken.mockRejectedValue(new Error('network'));
      renderCard();
      fireEvent.click(await screen.findByText('access.tunnel.shareMobile'));
      await waitFor(() => expect(doubles.toastError).toHaveBeenCalledWith('access.tunnel.error'));
      expect(doubles.writeToClipboard).not.toHaveBeenCalled();
    });

    it('offers to install the hub as an app when the browser allows it', async () => {
      doubles.pwa.isInstallable = true;
      await shareHubLink();
      fireEvent.click(screen.getByText('access.tunnel.pwaInstall'));
      expect(doubles.pwa.promptInstall).toHaveBeenCalledTimes(1);
    });

    it('confirms an installed hub app instead of offering it again', async () => {
      doubles.pwa.isInstalled = true;
      await shareHubLink();
      expect(screen.getByText('access.tunnel.pwaInstalled')).toBeInTheDocument();
      expect(screen.queryByText('access.tunnel.pwaInstall')).not.toBeInTheDocument();
    });

    it('stays quiet about installing when the browser cannot', async () => {
      await shareHubLink();
      expect(screen.queryByText('access.tunnel.pwaTitle')).not.toBeInTheDocument();
    });
  });

  describe('health check', () => {
    async function runCheck() {
      renderCard();
      fireEvent.click(await screen.findByText('access.ingress.testButton'));
    }

    it('tests the address the server reports before the stored one', async () => {
      doubles.getIngressUrl.mockResolvedValue('https://server.example.com');
      doubles.config.publicIngressBaseUrl = 'https://stored.example.com';
      await runCheck();
      await waitFor(() => expect(doubles.toastSuccess).toHaveBeenCalledWith('access.ingress.testSuccess'));
      expect(doubles.testIngressHealth).toHaveBeenCalledWith('https://server.example.com');
    });

    it('falls back to the stored address', async () => {
      doubles.config.publicIngressBaseUrl = INGRESS_URL;
      await runCheck();
      await waitFor(() => expect(doubles.testIngressHealth).toHaveBeenCalledWith(INGRESS_URL));
    });

    it.each([
      ['an unhealthy ingress', () => doubles.testIngressHealth.mockResolvedValue(false)],
      ['a failing check', () => doubles.testIngressHealth.mockRejectedValue(new Error('network'))],
    ])('reports %s', async (_label, arrange) => {
      doubles.config.publicIngressBaseUrl = INGRESS_URL;
      arrange();
      await runCheck();
      await waitFor(() => expect(doubles.toastError).toHaveBeenCalledWith('access.ingress.testFailed'));
    });

    it('asks for an address when none is configured', async () => {
      await runCheck();
      await waitFor(() => expect(doubles.toastError).toHaveBeenCalledWith('access.ingress.notConfigured'));
      expect(doubles.testIngressHealth).not.toHaveBeenCalled();
    });

    it('refuses an address that is not HTTPS', async () => {
      doubles.config.publicIngressBaseUrl = 'http://insecure.example.com';
      await runCheck();
      await waitFor(() => expect(doubles.toastError).toHaveBeenCalledWith('access.ingress.httpsRequired'));
      expect(doubles.testIngressHealth).not.toHaveBeenCalled();
    });

    it('locks the button while a check is running', async () => {
      doubles.config.publicIngressBaseUrl = INGRESS_URL;
      let finish: (healthy: boolean) => void = () => undefined;
      doubles.testIngressHealth.mockReturnValue(new Promise<boolean>((resolve) => (finish = resolve)));
      await runCheck();
      await waitFor(() => expect(buttonOf('access.ingress.testing')).toBeDisabled());
      finish(true);
      await waitFor(() => expect(buttonOf('access.ingress.testButton')).toBeEnabled());
    });
  });
});
