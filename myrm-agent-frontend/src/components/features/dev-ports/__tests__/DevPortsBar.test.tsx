/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DevPortsBar } from '../DevPortsBar';
import type { DevPortInfo } from '@/services/devPorts';
import * as devPortsService from '@/services/devPorts';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconServer: () => <span data-testid="icon-server" />,
  IconGlobe: () => <span data-testid="icon-globe" />,
  IconExternalLink: () => <span data-testid="icon-external" />,
  IconRefresh: () => <span data-testid="icon-refresh" />,
  IconMonitor: () => <span data-testid="icon-monitor" />,
  IconCopy: () => <span data-testid="icon-copy" />,
  IconCheck: () => <span data-testid="icon-check" />,
  IconTrash: () => <span data-testid="icon-trash" />,
  IconX: () => <span data-testid="icon-x" />,
}));

describe('DevPortsBar component', () => {
  const mockPorts: DevPortInfo[] = [
    {
      port: 3000,
      process_name: 'next-dev',
      pid: 4281,
      protocol: 'http',
      url: 'http://localhost:3000',
      tunnel_url: null,
      status: 'listening',
      created_at: '2026-10-12T07:00:00Z',
    },
    {
      port: 5173,
      process_name: 'vite',
      pid: 5129,
      protocol: 'http',
      url: 'http://localhost:5173',
      tunnel_url: null,
      status: 'listening',
      created_at: '2026-10-12T07:00:00Z',
    },
  ];

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
    vi.spyOn(devPortsService, 'listDevPorts').mockResolvedValue(mockPorts);
  });

  it('renders capsule button showing active ports count', async () => {
    render(<DevPortsBar />);

    await waitFor(() => {
      expect(screen.getByText('2 Ports')).toBeDefined();
    });
  });

  it('toggles popover when clicking capsule button', async () => {
    render(<DevPortsBar />);

    const barBtn = await screen.findByRole('button', {
      name: /barAriaLabel/i,
    });
    fireEvent.click(barBtn);

    expect(screen.getByText('modalTitle')).toBeDefined();
    expect(screen.getByText(':3000')).toBeDefined();
    expect(screen.getByText(':5173')).toBeDefined();
  });

  it('toggles popover on Cmd+Shift+P shortcut', async () => {
    render(<DevPortsBar />);

    await screen.findByText('2 Ports');

    fireEvent.keyDown(window, {
      key: 'p',
      metaKey: true,
      shiftKey: true,
    });

    expect(screen.getByText('modalTitle')).toBeDefined();

    // Toggle again to close
    fireEvent.keyDown(window, {
      key: 'p',
      metaKey: true,
      shiftKey: true,
    });

    expect(screen.queryByText('modalTitle')).toBeNull();
  });

  it('opens preview modal when clicking a port item card', async () => {
    render(<DevPortsBar />);

    const barBtn = await screen.findByRole('button', {
      name: /barAriaLabel/i,
    });
    fireEvent.click(barBtn);

    const portCard = screen.getByText(':3000');
    fireEvent.click(portCard);

    // Modal should now be open
    expect(screen.getByTitle('Preview port 3000')).toBeDefined();
  });

  it('terminates port when clicking trash button in card', async () => {
    vi.spyOn(devPortsService, 'closeDevPort').mockResolvedValueOnce({
      success: true,
    });

    render(<DevPortsBar />);

    const barBtn = await screen.findByRole('button', {
      name: /barAriaLabel/i,
    });
    fireEvent.click(barBtn);

    const trashButtons = screen.getAllByTitle('closePort');
    fireEvent.click(trashButtons[0]);

    await waitFor(() => {
      expect(devPortsService.closeDevPort).toHaveBeenCalledWith(3000);
      expect(screen.queryByText(':3000')).toBeNull();
      expect(screen.getByText(':5173')).toBeDefined();
    });
  });
});
