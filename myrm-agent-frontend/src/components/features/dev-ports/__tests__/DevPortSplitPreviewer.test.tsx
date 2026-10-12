import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DevPortSplitPreviewer } from '../DevPortSplitPreviewer';
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
  IconX: () => <span data-testid="icon-x" />,
  IconChevronDown: () => <span data-testid="icon-chevron-down" />,
  IconChevronUp: () => <span data-testid="icon-chevron-up" />,
}));

describe('DevPortSplitPreviewer component', () => {
  const samplePort: DevPortInfo = {
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
  });

  it('renders nothing when controlled isOpen is false', () => {
    const { container } = render(
      <DevPortSplitPreviewer isOpen={false} activePort={samplePort} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders split panel with iframe when controlled isOpen is true', () => {
    render(<DevPortSplitPreviewer isOpen={true} activePort={samplePort} />);

    expect(screen.getByTestId('dev-port-split-previewer')).toBeInTheDocument();
    expect(screen.getByText('next-dev')).toBeInTheDocument();
    expect(screen.getByText(':3000')).toBeInTheDocument();

    const iframe = screen.getByTitle('next-dev live preview');
    expect(iframe).toHaveAttribute('src', 'http://localhost:3000');
    expect(iframe).toHaveAttribute(
      'sandbox',
      'allow-scripts allow-same-origin allow-forms allow-popups',
    );
  });

  it('switches viewport modes between desktop, tablet and mobile', () => {
    render(<DevPortSplitPreviewer isOpen={true} activePort={samplePort} />);

    const tabletButton = screen.getByLabelText('viewportTablet');
    fireEvent.click(tabletButton);
    expect(tabletButton).toHaveClass('bg-zinc-800');

    const mobileButton = screen.getByLabelText('viewportMobile');
    fireEvent.click(mobileButton);
    expect(mobileButton).toHaveClass('bg-zinc-800');

    const desktopButton = screen.getByLabelText('viewportDesktop');
    fireEvent.click(desktopButton);
    expect(desktopButton).toHaveClass('bg-zinc-800');
  });

  it('generates and copies public tunnel URL on button click', async () => {
    const mockTunnelResponse = {
      port: 3000,
      tunnel_url: 'https://tunnel-3000.sandbox.myrm.io',
      expires_in_seconds: 3600,
    };
    vi.spyOn(devPortsService, 'createDevPortTunnel').mockResolvedValueOnce(
      mockTunnelResponse,
    );

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(<DevPortSplitPreviewer isOpen={true} activePort={samplePort} />);

    const copyButton = screen.getByLabelText('copyTunnel');
    fireEvent.click(copyButton);

    await waitFor(() => {
      expect(devPortsService.createDevPortTunnel).toHaveBeenCalledWith(3000);
      expect(writeTextMock).toHaveBeenCalledWith('https://tunnel-3000.sandbox.myrm.io');
    });
  });

  it('opens preview panel on global myrm:open-dev-port-preview event', async () => {
    render(<DevPortSplitPreviewer />);

    act(() => {
      window.dispatchEvent(
        new CustomEvent<DevPortInfo>('myrm:open-dev-port-preview', {
          detail: samplePort,
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('dev-port-split-previewer')).toBeInTheDocument();
      expect(screen.getByText('next-dev')).toBeInTheDocument();
    });
  });

  it('toggles console drawer and displays port metadata', () => {
    render(<DevPortSplitPreviewer isOpen={true} activePort={samplePort} />);

    expect(screen.queryByTestId('dev-port-console-drawer')).not.toBeInTheDocument();

    const toggleButton = screen.getByText('consoleDrawerTitle');
    fireEvent.click(toggleButton);

    expect(screen.getByTestId('dev-port-console-drawer')).toBeInTheDocument();
    expect(
      screen.getByText(/Service started on port 3000/i),
    ).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', () => {
    const onCloseMock = vi.fn();
    render(
      <DevPortSplitPreviewer
        isOpen={true}
        activePort={samplePort}
        onClose={onCloseMock}
      />,
    );

    const closeButton = screen.getByLabelText('closeAriaLabel');
    fireEvent.click(closeButton);

    expect(onCloseMock).toHaveBeenCalledTimes(1);
  });
});
