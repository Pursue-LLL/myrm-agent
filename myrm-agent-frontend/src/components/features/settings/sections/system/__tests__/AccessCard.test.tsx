import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AccessCard } from '../AccessCard';
import { PORT, cardProps, doubles, requirement, resetDoubles, type CardOptions } from './accessCardTestKit';

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

describe('AccessCard', () => {
  beforeEach(resetDoubles);

  describe('availability', () => {
    it('shows only a notice when web access is off and the app is not in local mode', () => {
      doubles.isLocalMode.mockReturnValue(false);
      renderCard({ config: { enableWebUIMode: false } });
      expect(screen.getByText('access.disabled')).toBeInTheDocument();
      expect(screen.queryByText('access.local')).not.toBeInTheDocument();
    });

    it('treats browser development in local mode as enabled', () => {
      doubles.isTauriRuntime.mockReturnValue(false);
      renderCard({ config: { enableWebUIMode: false } });
      expect(screen.getByText('access.local')).toBeInTheDocument();
      expect(screen.queryByText('access.disabled')).not.toBeInTheDocument();
    });

    it('offers just the local address outside local mode', () => {
      doubles.isLocalMode.mockReturnValue(false);
      renderCard();
      expect(screen.getByText(`http://localhost:${PORT}`)).toBeInTheDocument();
      expect(screen.queryByText('access.lan.title')).not.toBeInTheDocument();
      expect(screen.queryByText('access.ingress.title')).not.toBeInTheDocument();
      expect(doubles.getLocalNetwork).not.toHaveBeenCalled();
      expect(doubles.getTunnelStatus).not.toHaveBeenCalled();
    });

    it('follows the port of the page in the browser', async () => {
      doubles.isTauriRuntime.mockReturnValue(false);
      renderCard();
      const pagePort = Number.parseInt(window.location.port, 10) || PORT;
      await waitFor(() => expect(doubles.getLocalNetwork).toHaveBeenCalledWith(pagePort));
      expect(screen.getByText(`http://localhost:${pagePort}`)).toBeInTheDocument();
    });
  });

  describe('addresses', () => {
    it('copies and opens the local address', () => {
      const open = vi.spyOn(window, 'open').mockReturnValue(null);
      renderCard();
      fireEvent.click(screen.getAllByTitle('access.copy')[0]);
      expect(doubles.writeToClipboard).toHaveBeenCalledWith(`http://localhost:${PORT}`);
      expect(doubles.toastSuccess).toHaveBeenCalledWith('copied');
      fireEvent.click(screen.getAllByTitle('access.open')[0]);
      expect(open).toHaveBeenCalledWith(`http://localhost:${PORT}`, '_blank', 'noopener,noreferrer');
      open.mockRestore();
    });

    it('builds the LAN address and its QR code from the detected IP', () => {
      renderCard({ localIP: '192.168.1.8' });
      expect(screen.getByText(`http://192.168.1.8:${PORT}`)).toBeInTheDocument();
      expect(screen.getByAltText('access.lan.qrAlt')).toHaveAttribute(
        'src',
        `/webui/qrcode.png?host=192.168.1.8&port=${PORT}`,
      );
    });

    it('falls back to the server-reported LAN address when no IP is known', async () => {
      doubles.getLocalNetwork.mockResolvedValue({ ip: '', url: 'http://10.0.0.5:8080', hint: '' });
      renderCard({ localIP: '' });
      expect(screen.getByText('access.fetchingIP')).toBeInTheDocument();
      expect(await screen.findByText('http://10.0.0.5:8080')).toBeInTheDocument();
      expect(doubles.getLocalNetwork).toHaveBeenCalledWith(PORT);
      expect(screen.getByAltText('access.lan.qrAlt')).toHaveAttribute(
        'src',
        `/webui/qrcode.png?url=${encodeURIComponent('http://10.0.0.5:8080')}`,
      );
    });

    it.each([
      ['the desktop shell has remote access off', true, { enableRemoteAccess: false }, 'access.lan.tauriEnableRemote'],
      ['the page runs in a browser', false, {}, 'access.lan.webDevHint'],
    ])('hints at what to enable when %s', (_label, tauri, config, hint) => {
      doubles.isTauriRuntime.mockReturnValue(tauri);
      renderCard({ config });
      expect(screen.getByText(hint)).toBeInTheDocument();
    });

    it('warns when the desktop shell exposes remote access without a password', () => {
      renderCard({ config: { requirePassword: false, enableRemoteAccess: true } });
      expect(screen.getByText('access.securityWarning')).toBeInTheDocument();
    });

    it('stays quiet when a password protects remote access', () => {
      renderCard({ config: { requirePassword: true, enableRemoteAccess: true } });
      expect(screen.queryByText('access.securityWarning')).not.toBeInTheDocument();
    });
  });

  describe('public ingress guidance', () => {
    it.each([
      ['required', requirement(true), 'access.guide.publicIngressRequired', 'access.guide.publicIngressOptional'],
      ['optional', requirement(false), 'access.guide.publicIngressOptional', 'access.guide.publicIngressRequired'],
    ])('explains public ingress as %s', (_label, ingress, shown, hidden) => {
      renderCard({ ingress });
      expect(screen.getByText(shown)).toBeInTheDocument();
      expect(screen.queryByText(hidden)).not.toBeInTheDocument();
    });

    it('says nothing about the ingress requirement until it is known', () => {
      renderCard({ ingress: null });
      expect(screen.getByText('access.guide.lanFirst')).toBeInTheDocument();
      expect(screen.queryByText('access.guide.publicIngressRequired')).not.toBeInTheDocument();
      expect(screen.queryByText('access.guide.publicIngressOptional')).not.toBeInTheDocument();
    });

    it('badges the ingress card only when the ingress is required', () => {
      const { unmount } = renderCard({ ingress: requirement(true) });
      expect(screen.getByText('access.ingress.requiredBadge')).toBeInTheDocument();
      unmount();
      renderCard({ ingress: requirement(false) });
      expect(screen.queryByText('access.ingress.requiredBadge')).not.toBeInTheDocument();
    });
  });
});
