import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import {
  CrossChannelFootprintFabricView,
  getChannelIcon,
  getCategoryIcon,
} from '../CrossChannelFootprintFabricView';
import { WeeklyDigestSynthesizerModal } from '../WeeklyDigestSynthesizerModal';
import { useWeeklyDigestStore } from '../useWeeklyDigestStore';
import { INITIAL_CHANNEL_FOOTPRINTS } from '../footprintAggregatorData';

describe('Weekly Digest Context Fabric Components', () => {
  beforeEach(() => {
    act(() => {
      useWeeklyDigestStore.getState().resetState();
    });
  });

  describe('Icon Helper Pure Functions', () => {
    it('returns valid icon elements for channels and categories', () => {
      expect(getChannelIcon('feishu')).toBeDefined();
      expect(getChannelIcon('wechat')).toBeDefined();
      expect(getChannelIcon('desktop')).toBeDefined();
      expect(getChannelIcon('cli')).toBeDefined();
      expect(getChannelIcon('web')).toBeDefined();

      expect(getCategoryIcon('pr-review')).toBeDefined();
      expect(getCategoryIcon('deliverable')).toBeDefined();
      expect(getCategoryIcon('rfc-decision')).toBeDefined();
      expect(getCategoryIcon('learning')).toBeDefined();
      expect(getCategoryIcon('risk-roadblock')).toBeDefined();
    });
  });

  describe('CrossChannelFootprintFabricView Component', () => {
    it('renders the footprint fabric board with stats and items', () => {
      render(<CrossChannelFootprintFabricView />);

      expect(screen.getByTestId('footprint-fabric-view')).toBeInTheDocument();
      expect(screen.getByText('全域工作足迹汇聚看板')).toBeInTheDocument();
      expect(screen.getByText('2026-W36')).toBeInTheDocument();
      expect(
        screen.getByText('PR #402 交易网关零拷贝通道 Review')
      ).toBeInTheDocument();
      expect(
        screen.getByText('Tauri 桌面端 PTY 真实多终端会话池交付')
      ).toBeInTheDocument();
    });

    it('filters footprints by channel tab', () => {
      render(<CrossChannelFootprintFabricView />);

      const feishuTab = screen.getByRole('tab', { name: /飞书/ });
      fireEvent.click(feishuTab);

      expect(useWeeklyDigestStore.getState().selectedChannelFilter).toBe('feishu');
      expect(
        screen.getByText('PR #402 交易网关零拷贝通道 Review')
      ).toBeInTheDocument();
      expect(
        screen.queryByText('Tauri 桌面端 PTY 真实多终端会话池交付')
      ).toBeNull();
    });

    it('filters footprints by category button', () => {
      render(<CrossChannelFootprintFabricView />);

      const deliverableBtn = screen.getByRole('button', { name: '核心交付' });
      fireEvent.click(deliverableBtn);

      expect(useWeeklyDigestStore.getState().selectedCategoryFilter).toBe('deliverable');
      expect(
        screen.getByText('Tauri 桌面端 PTY 真实多终端会话池交付')
      ).toBeInTheDocument();
      expect(
        screen.queryByText('PR #402 交易网关零拷贝通道 Review')
      ).toBeNull();
    });

    it('toggles footprint item inclusion via checkbox button', () => {
      render(<CrossChannelFootprintFabricView />);

      const toggleButtons = screen.getAllByRole('button', { name: '从周报中排除' });
      fireEvent.click(toggleButtons[0]);

      expect(
        useWeeklyDigestStore.getState().footprints[0].includedInDigest
      ).toBe(false);
    });

    it('toggles select all and deselect all button', () => {
      render(<CrossChannelFootprintFabricView />);

      const toggleAllBtn = screen.getByRole('button', { name: /取消全选/ });
      fireEvent.click(toggleAllBtn);

      expect(
        useWeeklyDigestStore.getState().footprints.every((f) => !f.includedInDigest)
      ).toBe(true);

      const selectAllBtn = screen.getByRole('button', { name: /全选纳入/ });
      fireEvent.click(selectAllBtn);

      expect(
        useWeeklyDigestStore.getState().footprints.every((f) => f.includedInDigest)
      ).toBe(true);
    });

    it('opens synthesizer modal on button click', () => {
      render(<CrossChannelFootprintFabricView />);

      const synthBtn = screen.getByRole('button', { name: '一键合成工作周报' });
      fireEvent.click(synthBtn);

      expect(useWeeklyDigestStore.getState().isSynthesizerModalOpen).toBe(true);
    });
  });

  describe('WeeklyDigestSynthesizerModal Component', () => {
    it('does not render when isSynthesizerModalOpen is false', () => {
      render(<WeeklyDigestSynthesizerModal />);
      expect(screen.queryByTestId('weekly-digest-synthesizer-modal')).toBeNull();
    });

    it('renders modal with synthesized content and style tabs', () => {
      act(() => {
        useWeeklyDigestStore.getState().openSynthesizerModal();
      });

      render(<WeeklyDigestSynthesizerModal />);

      expect(
        screen.getByTestId('weekly-digest-synthesizer-modal')
      ).toBeInTheDocument();
      expect(
        screen.getByText('全自动工作周报合成与复盘中心')
      ).toBeInTheDocument();
      expect(screen.getByTestId('digest-preview-content')).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: '高管审阅版' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: '研发技术向' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: '极简子弹点' })).toBeInTheDocument();
    });

    it('switches style preset when clicking tabs', async () => {
      act(() => {
        useWeeklyDigestStore.getState().openSynthesizerModal();
      });

      render(<WeeklyDigestSynthesizerModal />);

      const techTab = screen.getByRole('tab', { name: '研发技术向' });
      fireEvent.click(techTab);

      await waitFor(() => {
        expect(useWeeklyDigestStore.getState().activeStylePreset).toBe('technical');
      });
    });

    it('submits a refinement prompt and updates the preview', async () => {
      act(() => {
        useWeeklyDigestStore.getState().openSynthesizerModal();
      });

      render(<WeeklyDigestSynthesizerModal />);

      const input = screen.getByPlaceholderText(/输入自然语言微调周报/);
      const submitBtn = screen.getByRole('button', { name: '发送微调指令' });

      fireEvent.change(input, { target: { value: '切换为极简子弹点' } });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(useWeeklyDigestStore.getState().activeStylePreset).toBe('bullet');
      });
    });

    it('handles clipboard copy and shows feedback badge', async () => {
      act(() => {
        useWeeklyDigestStore.getState().openSynthesizerModal();
      });

      // Mock navigator.clipboard
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      vi.stubGlobal('navigator', {
        clipboard: { writeText: writeTextMock },
      });

      render(<WeeklyDigestSynthesizerModal />);

      const copyBtn = screen.getByRole('button', { name: '复制周报 Markdown' });
      fireEvent.click(copyBtn);

      await waitFor(() => {
        expect(screen.getByText('已复制')).toBeInTheDocument();
      });
    });

    it('handles feishu export and displays success status indicator', async () => {
      act(() => {
        useWeeklyDigestStore.getState().openSynthesizerModal();
      });

      render(<WeeklyDigestSynthesizerModal />);

      const feishuBtn = screen.getByRole('button', { name: '直落导出到飞书文档' });
      fireEvent.click(feishuBtn);

      await waitFor(() => {
        expect(screen.getByText(/成功处理投递目标：feishu/)).toBeInTheDocument();
      });
    });

    it('closes modal when clicking close button', () => {
      act(() => {
        useWeeklyDigestStore.getState().openSynthesizerModal();
      });

      render(<WeeklyDigestSynthesizerModal />);

      const closeBtn = screen.getByRole('button', { name: '关闭周报弹窗' });
      fireEvent.click(closeBtn);

      expect(useWeeklyDigestStore.getState().isSynthesizerModalOpen).toBe(false);
    });
  });
});
