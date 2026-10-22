import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ZeroConfigMobilePairingModal } from '../ZeroConfigMobilePairingModal';

describe('ZeroConfigMobilePairingModal', () => {
  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <ZeroConfigMobilePairingModal isOpen={false} onClose={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders pairing modal with title, qr code area, and countdown', () => {
    render(<ZeroConfigMobilePairingModal isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByText('免配置移动伴侣扫码网关')).toBeDefined();
    expect(screen.getByTestId('mock-qr-code')).toBeDefined();
    expect(screen.getByText(/打开手机 App 扫描上方二维码/)).toBeDefined();
    expect(screen.getByText('飞书')).toBeDefined();
    expect(screen.getByText('企业微信')).toBeDefined();
  });

  it('switches channel when clicking channel buttons', () => {
    render(<ZeroConfigMobilePairingModal isOpen={true} onClose={vi.fn()} />);

    const wechatBtn = screen.getByText('企业微信');
    fireEvent.click(wechatBtn);

    expect(screen.getByText(/扫码连接 wechat_work/)).toBeDefined();
  });

  it('transitions to paired companion state on simulation scan and handles disconnect', () => {
    render(<ZeroConfigMobilePairingModal isOpen={true} onClose={vi.fn()} />);

    const simBtn = screen.getByTestId('simulate-scan-auth-btn');
    fireEvent.click(simBtn);

    expect(screen.getByText('移动伴侣已安全绑定')).toBeDefined();
    expect(screen.getByText(/离线云端中继：/)).toBeDefined();
    expect(screen.getByText('已开启 · 随走随用')).toBeDefined();

    // Disconnect
    const disconnectBtn = screen.getByRole('button', { name: '解绑当前伴侣设备' });
    fireEvent.click(disconnectBtn);

    expect(screen.getByText(/打开手机 App 扫描上方二维码/)).toBeDefined();
  });

  it('handles close button click and escape key', () => {
    const onClose = vi.fn();
    render(<ZeroConfigMobilePairingModal isOpen={true} onClose={onClose} />);

    const closeBtn = screen.getByRole('button', { name: '关闭扫码弹窗' });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
