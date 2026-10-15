import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { UnattendedRejoinStatusHUD } from '../UnattendedRejoinStatusHUD';
import { SourcedResultChecklistModal } from '../SourcedResultChecklistModal';
import { useLongTaskNotifyStore } from '../useLongTaskNotifyStore';

describe('UnattendedRejoinStatusHUD and SourcedResultChecklistModal components', () => {
  beforeEach(() => {
    act(() => {
      useLongTaskNotifyStore.getState().resetState();
    });
  });

  describe('UnattendedRejoinStatusHUD', () => {
    it('renders task title, progress, step description and environment pill', () => {
      render(<UnattendedRejoinStatusHUD />);

      expect(
        screen.getByTestId('unattended-rejoin-status-hud')
      ).toBeInTheDocument();
      expect(
        screen.getByText('全网竞品商业模式深度调研与沙箱压测报告')
      ).toBeInTheDocument();
      expect(screen.getByText('无人值守持续运行中')).toBeInTheDocument();
      expect(screen.getByText('65%')).toBeInTheDocument();
      expect(screen.getByText('常驻云端沙箱')).toBeInTheDocument();
      expect(
        screen.getByText('第3步：正在生成各家厂商SLA与技术差异雷达图')
      ).toBeInTheDocument();
    });

    it('displays backgrounded pill when phone is locked or backgrounded', () => {
      act(() => {
        useLongTaskNotifyStore.getState().toggleBackgroundMode(true);
      });

      render(<UnattendedRejoinStatusHUD />);
      expect(
        screen.getByText('手机已切后台/锁屏保活')
      ).toBeInTheDocument();
    });

    it('triggers rejoin sync on button click', () => {
      render(<UnattendedRejoinStatusHUD />);

      const rejoinBtn = screen.getByRole('button', {
        name: '断点重连增量同步',
      });
      act(() => {
        fireEvent.click(rejoinBtn);
      });

      expect(useLongTaskNotifyStore.getState().isBackgrounded).toBe(false);
    });

    it('completes task and opens review modal via button', () => {
      render(<UnattendedRejoinStatusHUD />);

      const completeBtn = screen.getByRole('button', {
        name: '模拟任务完成',
      });
      act(() => {
        fireEvent.click(completeBtn);
      });

      expect(useLongTaskNotifyStore.getState().activeTask?.status).toBe(
        'completed'
      );
      expect(useLongTaskNotifyStore.getState().isReviewModalOpen).toBe(true);
    });
  });

  describe('SourcedResultChecklistModal', () => {
    it('returns null when review modal is closed', () => {
      const { container } = render(<SourcedResultChecklistModal />);
      expect(container.firstChild).toBeNull();
    });

    it('renders review modal with checklist items, source links and verified badges', () => {
      act(() => {
        useLongTaskNotifyStore.getState().openReviewModal();
      });

      render(<SourcedResultChecklistModal />);

      expect(
        screen.getByTestId('sourced-result-checklist-modal')
      ).toBeInTheDocument();
      expect(
        screen.getByText('长任务结果复盘 · 带来源权威清单')
      ).toBeInTheDocument();
      expect(screen.getByText(/已核验 2 项/)).toBeInTheDocument();
      expect(
        screen.getByText('全量竞品定价与阶梯策略对比矩阵')
      ).toBeInTheDocument();
      expect(
        screen.getByText('云端沙箱合规与SOC2审计条款')
      ).toBeInTheDocument();
    });

    it('copies source url to clipboard on copy button click', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: {
          writeText: writeTextMock,
        },
      });

      act(() => {
        useLongTaskNotifyStore.getState().openReviewModal();
      });

      render(<SourcedResultChecklistModal />);

      const copyBtn = screen.getByRole('button', {
        name: '复制 全量竞品定价与阶梯策略对比矩阵 来源链接',
      });
      await act(async () => {
        fireEvent.click(copyBtn);
      });

      expect(writeTextMock).toHaveBeenCalledWith(
        'https://benchmark.enterprise.ai/pricing/q3-matrix'
      );
    });

    it('closes review modal when close button is clicked', () => {
      act(() => {
        useLongTaskNotifyStore.getState().openReviewModal();
      });

      render(<SourcedResultChecklistModal />);

      const closeBtn = screen.getByRole('button', {
        name: '关闭清单复盘窗口',
      });
      act(() => {
        fireEvent.click(closeBtn);
      });

      expect(useLongTaskNotifyStore.getState().isReviewModalOpen).toBe(false);
    });
  });
});
