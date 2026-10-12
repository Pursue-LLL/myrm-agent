/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DevPortIndicator } from '../DevPortIndicator';
import type { DevPortInfo } from '@/services/devPorts';
import * as devPortsService from '@/services/devPorts';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconServer: () => <span data-testid="icon-server" />,
  IconExternalLink: () => <span data-testid="icon-external" />,
  IconMonitor: () => <span data-testid="icon-monitor" />,
}));

describe('DevPortIndicator component', () => {
  const samplePort: DevPortInfo = {
    port: 3000,
    process_name: 'next-dev',
    pid: 1024,
    protocol: 'http',
    url: 'http://localhost:3000',
    tunnel_url: 'https://tunnel-3000.sandbox.myrm.io',
    status: 'listening',
    created_at: '2026-10-12T07:00:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when neither portInfo nor rawLogs are provided', () => {
    const { container } = render(<DevPortIndicator />);
    expect(container.firstChild).toBeNull();
  });

  it('renders badge with port and process name when portInfo is passed', () => {
    render(<DevPortIndicator portInfo={samplePort} />);

    expect(screen.getByTestId('dev-port-indicator')).toBeInTheDocument();
    expect(screen.getByText('next-dev')).toBeInTheDocument();
    expect(screen.getByText(':3000')).toBeInTheDocument();
    expect(screen.getByText('indicatorReady')).toBeInTheDocument();
  });

  it('fires onPreview and dispatches global event on preview click', () => {
    const onPreviewMock = vi.fn();
    const eventSpy = vi.fn();
    window.addEventListener('myrm:open-dev-port-preview', eventSpy);

    render(<DevPortIndicator portInfo={samplePort} onPreview={onPreviewMock} />);

    const previewButton = screen.getByRole('button', { name: /indicatorPreview 3000/i });
    fireEvent.click(previewButton);

    expect(onPreviewMock).toHaveBeenCalledTimes(1);
    expect(onPreviewMock).toHaveBeenCalledWith(samplePort);
    expect(eventSpy).toHaveBeenCalledTimes(1);

    window.removeEventListener('myrm:open-dev-port-preview', eventSpy);
  });

  it('automatically sniffs ports from rawLogs and displays indicator', async () => {
    const rawLogs = 'Ready on http://localhost:5173';
    const sniffedPort: DevPortInfo = {
      port: 5173,
      process_name: 'vite',
      pid: null,
      protocol: 'http',
      url: 'http://localhost:5173',
      tunnel_url: null,
      status: 'listening',
      created_at: '2026-10-12T07:00:00Z',
    };

    vi.spyOn(devPortsService, 'sniffAndRegisterDevPorts').mockResolvedValueOnce([sniffedPort]);

    render(<DevPortIndicator rawLogs={rawLogs} />);

    await waitFor(() => {
      expect(screen.getByText('vite')).toBeInTheDocument();
      expect(screen.getByText(':5173')).toBeInTheDocument();
    });
  });
});
