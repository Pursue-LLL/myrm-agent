import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { HumanTakeoverControlOverlay } from '../HumanTakeoverControlOverlay';
import { EphemeralShareModal } from '../EphemeralShareModal';
import { useRemoteDesktopStore } from '../useRemoteDesktopStore';

describe('HumanTakeoverControlOverlay and EphemeralShareModal components', () => {
  beforeEach(() => {
    act(() => {
      useRemoteDesktopStore.getState().resetState();
    });
  });

  describe('HumanTakeoverControlOverlay', () => {
    it('returns null when there is no alert and control mode is observer', () => {
      const { container } = render(<HumanTakeoverControlOverlay />);
      expect(container.firstChild).toBeNull();
    });

    it('renders alert when AI triggers takeover request', () => {
      act(() => {
        useRemoteDesktopStore
          .getState()
          .requestHumanTakeover('遇到银行级别的双因素身份验证');
      });

      render(<HumanTakeoverControlOverlay />);

      expect(
        screen.getByTestId('human-takeover-control-overlay')
      ).toBeInTheDocument();
      expect(screen.getByText('遇到银行级别的双因素身份验证')).toBeInTheDocument();
      expect(screen.getByText('您当前正在人工接管中')).toBeInTheDocument();
      expect(screen.getByText('控制权锁定')).toBeInTheDocument();

      const releaseBtn = screen.getByRole('button', {
        name: '确认完成并交回 Agent 自动执行',
      });
      fireEvent.click(releaseBtn);

      expect(useRemoteDesktopStore.getState().controlMode).toBe('observer');
      expect(useRemoteDesktopStore.getState().isTakeoverAlertActive).toBe(false);
    });

    it('allows taking over control when alert is pending', () => {
      act(() => {
        useRemoteDesktopStore.setState({
          isTakeoverAlertActive: true,
          controlMode: 'observer',
          takeoverReason: '云端沙箱触发交互挑战',
        });
      });

      render(<HumanTakeoverControlOverlay />);

      expect(screen.getByText('AI 请求人工介入接管')).toBeInTheDocument();
      expect(screen.getByText('等待响应')).toBeInTheDocument();

      const takeOverBtn = screen.getByRole('button', { name: '立即接管控制权' });
      fireEvent.click(takeOverBtn);

      expect(useRemoteDesktopStore.getState().controlMode).toBe('human-takeover');
    });

    it('allows dismissing the alert without taking over', () => {
      act(() => {
        useRemoteDesktopStore.setState({
          isTakeoverAlertActive: true,
          controlMode: 'observer',
          takeoverReason: '建议检查',
        });
      });

      render(<HumanTakeoverControlOverlay />);

      const dismissBtn = screen.getByRole('button', {
        name: '忽略介入请求并让 Agent 继续',
      });
      fireEvent.click(dismissBtn);

      expect(useRemoteDesktopStore.getState().isTakeoverAlertActive).toBe(false);
      expect(useRemoteDesktopStore.getState().controlMode).toBe('observer');
    });
  });

  describe('EphemeralShareModal', () => {
    it('returns null when modal is not open', () => {
      const { container } = render(<EphemeralShareModal />);
      expect(container.firstChild).toBeNull();
    });

    it('renders modal dialog with ticket info when open', () => {
      act(() => {
        useRemoteDesktopStore.getState().openShareModal();
      });

      render(<EphemeralShareModal />);

      expect(screen.getByTestId('ephemeral-share-modal')).toBeInTheDocument();
      expect(screen.getByText('免登录时效安全分享链接')).toBeInTheDocument();
      const ticketUrl = useRemoteDesktopStore.getState().currentTicket?.url ?? '';
      expect(screen.getByDisplayValue(ticketUrl)).toBeInTheDocument();
      expect(screen.getByText(/有效期至：/)).toBeInTheDocument();
    });

    it('copies share url to clipboard', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: {
          writeText: writeTextMock,
        },
      });

      act(() => {
        useRemoteDesktopStore.getState().openShareModal();
      });

      render(<EphemeralShareModal />);

      const copyBtn = screen.getByRole('button', { name: '复制时效分享链接' });
      await act(async () => {
        fireEvent.click(copyBtn);
      });

      const ticketUrl = useRemoteDesktopStore.getState().currentTicket?.url ?? '';
      expect(writeTextMock).toHaveBeenCalledWith(ticketUrl);
      expect(screen.getByText('已复制')).toBeInTheDocument();
    });

    it('regenerates ticket with modified TTL and takeover options', () => {
      act(() => {
        useRemoteDesktopStore.getState().openShareModal();
      });

      render(<EphemeralShareModal />);

      const ttl24hBtn = screen.getByText('24 小时');
      fireEvent.click(ttl24hBtn);

      const takeoverCheckbox = screen.getByLabelText(
        '允许访客双向接管远程桌面（默认仅允许单向旁听观看）'
      );
      fireEvent.click(takeoverCheckbox);

      const oneTimeCheckbox = screen.getByLabelText(
        '单次访问后立即销毁凭据 (One-time Ephemeral)'
      );
      fireEvent.click(oneTimeCheckbox);

      const regenBtn = screen.getByRole('button', { name: '刷新并重新生成凭证' });
      fireEvent.click(regenBtn);

      const currentTicket = useRemoteDesktopStore.getState().currentTicket;
      expect(currentTicket?.allowTakeover).toBe(true);
      expect(currentTicket?.oneTimeOnly).toBe(true);
    });

    it('closes modal on close button click', () => {
      act(() => {
        useRemoteDesktopStore.getState().openShareModal();
      });

      render(<EphemeralShareModal />);

      const closeHeaderBtn = screen.getByRole('button', { name: '关闭分享窗口' });
      fireEvent.click(closeHeaderBtn);

      expect(useRemoteDesktopStore.getState().isShareModalOpen).toBe(false);
    });
  });
});
