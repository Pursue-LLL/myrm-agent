/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DevPortPreviewModal } from '../DevPortPreviewModal';
import type { DevPortInfo } from '@/services/devPorts';
import * as devPortsService from '@/services/devPorts';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconGlobe: () => <span data-testid="icon-globe" />,
  IconExternalLink: () => <span data-testid="icon-external" />,
  IconRefresh: () => <span data-testid="icon-refresh" />,
  IconMonitor: () => <span data-testid="icon-monitor" />,
  IconCopy: () => <span data-testid="icon-copy" />,
  IconCheck: () => <span data-testid="icon-check" />,
  IconTrash: () => <span data-testid="icon-trash" />,
  IconX: () => <span data-testid="icon-x" />,
}));

describe('DevPortPreviewModal component', () => {
  const mockPortInfo: DevPortInfo = {
    port: 3000,
    process_name: 'next-dev',
    pid: 1234,
    protocol: 'http',
    url: 'http://localhost:3000',
    tunnel_url: null,
    status: 'listening',
    created_at: '2026-10-12T07:00:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = function showModalMock(
        this: HTMLDialogElement,
      ) {
        this.open = true;
      };
    }
    if (!HTMLDialogElement.prototype.close) {
      HTMLDialogElement.prototype.close = function closeMock(
        this: HTMLDialogElement,
      ) {
        this.open = false;
      };
    }

    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it('renders nothing when isOpen is false or portInfo is null', () => {
    const { container: c1 } = render(
      <DevPortPreviewModal
        isOpen={false}
        portInfo={mockPortInfo}
        onClose={vi.fn()}
      />,
    );
    expect(c1.innerHTML).toBe('');

    const { container: c2 } = render(
      <DevPortPreviewModal isOpen={true} portInfo={null} onClose={vi.fn()} />,
    );
    expect(c2.innerHTML).toBe('');
  });

  it('renders port details and iframe preview when open', () => {
    render(
      <DevPortPreviewModal
        isOpen={true}
        portInfo={mockPortInfo}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText(':3000')).toBeDefined();
    expect(screen.getByText('(next-dev)')).toBeDefined();

    const iframe = screen.getByTitle('Preview port 3000') as HTMLIFrameElement;
    expect(iframe).toBeDefined();
    expect(iframe.src).toContain('http://localhost:3000');
  });

  it('switches viewport when clicking viewport controls', () => {
    render(
      <DevPortPreviewModal
        isOpen={true}
        portInfo={mockPortInfo}
        onClose={vi.fn()}
      />,
    );

    const tabletBtn = screen.getByRole('button', { name: /viewportTablet/i });
    fireEvent.click(tabletBtn);

    const mobileBtn = screen.getByRole('button', { name: /viewportMobile/i });
    fireEvent.click(mobileBtn);

    const desktopBtn = screen.getByRole('button', { name: /viewportDesktop/i });
    fireEvent.click(desktopBtn);
    expect(desktopBtn).toBeDefined();
  });

  it('copies tunnel URL and creates tunnel if not present', async () => {
    vi.spyOn(devPortsService, 'createDevPortTunnel').mockResolvedValueOnce({
      port: 3000,
      tunnel_url: 'https://preview-tunnel-3000.sandbox.myrm.io',
      expires_in_seconds: 3600,
    });

    render(
      <DevPortPreviewModal
        isOpen={true}
        portInfo={mockPortInfo}
        onClose={vi.fn()}
      />,
    );

    const tunnelBtn = screen.getByTitle('copyTunnel');
    fireEvent.click(tunnelBtn);

    await waitFor(() => {
      expect(devPortsService.createDevPortTunnel).toHaveBeenCalledWith(3000);
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        'https://preview-tunnel-3000.sandbox.myrm.io',
      );
    });
  });

  it('terminates port service and calls callbacks', async () => {
    vi.spyOn(devPortsService, 'closeDevPort').mockResolvedValueOnce({
      success: true,
    });
    const handleClose = vi.fn();
    const handleTerminated = vi.fn();

    render(
      <DevPortPreviewModal
        isOpen={true}
        portInfo={mockPortInfo}
        onClose={handleClose}
        onPortTerminated={handleTerminated}
      />,
    );

    const trashBtn = screen.getByTitle('closePort');
    fireEvent.click(trashBtn);

    await waitFor(() => {
      expect(devPortsService.closeDevPort).toHaveBeenCalledWith(3000);
      expect(handleTerminated).toHaveBeenCalledWith(3000);
      expect(handleClose).toHaveBeenCalled();
    });
  });
});
