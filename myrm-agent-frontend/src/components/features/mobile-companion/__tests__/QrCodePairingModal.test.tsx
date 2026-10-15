import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { QrCodePairingModal } from '../QrCodePairingModal';
import { useMobileCompanionStore } from '../useMobileCompanionStore';

describe('QrCodePairingModal', () => {
  beforeEach(() => {
    useMobileCompanionStore.setState({
      isPairingModalOpen: false,
      pairingConfig: null,
    });
  });

  it('renders nothing when closed or no pairing config', () => {
    const { container } = render(<QrCodePairingModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders QR code modal content when open', () => {
    useMobileCompanionStore.setState({
      isPairingModalOpen: true,
      pairingConfig: {
        pairingUrl: 'https://companion.example.com/pwa?token=tok-12345',
        token: 'tok-12345',
        expiresAt: Date.now() + 1800000,
        wsEndpoint: 'wss://companion.example.com/ws',
      },
    });

    render(<QrCodePairingModal />);
    expect(screen.getByTestId('qr-code-pairing-modal')).toBeInTheDocument();
    expect(screen.getByText('手机扫码随行带走长任务')).toBeInTheDocument();
    expect(screen.getByText('https://companion.example.com/pwa?token=tok-12345')).toBeInTheDocument();
    expect(screen.getByText('安全临时 Token，30 分钟内扫码有效')).toBeInTheDocument();
  });

  it('handles close button click and triggers callback', () => {
    const onCloseMock = vi.fn();
    useMobileCompanionStore.setState({
      isPairingModalOpen: true,
      pairingConfig: {
        pairingUrl: 'https://companion.example.com/pwa?token=tok-12345',
        token: 'tok-12345',
        expiresAt: Date.now() + 1800000,
        wsEndpoint: 'wss://companion.example.com/ws',
      },
    });

    render(<QrCodePairingModal onClose={onCloseMock} />);
    const closeBtn = screen.getByRole('button', { name: '' });
    fireEvent.click(closeBtn);

    expect(useMobileCompanionStore.getState().isPairingModalOpen).toBe(false);
    expect(onCloseMock).toHaveBeenCalledTimes(1);
  });

  it('handles copy url to clipboard', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    useMobileCompanionStore.setState({
      isPairingModalOpen: true,
      pairingConfig: {
        pairingUrl: 'https://companion.example.com/pwa?token=tok-12345',
        token: 'tok-12345',
        expiresAt: Date.now() + 1800000,
        wsEndpoint: 'wss://companion.example.com/ws',
      },
    });

    render(<QrCodePairingModal />);
    const copyBtn = screen.getByTitle('复制随行直链');
    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalledWith('https://companion.example.com/pwa?token=tok-12345');
    expect(screen.getByText('已复制到剪贴板')).toBeInTheDocument();
  });
});
