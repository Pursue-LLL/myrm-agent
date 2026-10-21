import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SpotlightPlaygroundModal } from '../SpotlightPlaygroundModal';
import { SpotlightMountConfirmModal } from '../SpotlightMountConfirmModal';
import { useModelSpotlightStore } from '../useModelSpotlightStore';
import { SPOTLIGHT_CATALOG } from '../spotlightCatalogData';

describe('SpotlightPlaygroundModal & SpotlightMountConfirmModal', () => {
  const sampleSpotlight = SPOTLIGHT_CATALOG[0]; // GPT-6 Astra

  beforeEach(() => {
    useModelSpotlightStore.getState().restoreDismissedSpotlights();
    useModelSpotlightStore.getState().closePlayground();
    useModelSpotlightStore.getState().closeMountModal();
    useModelSpotlightStore.getState().clearPlayground();
    useModelSpotlightStore.getState().setCurrentAgentModelId('openai/gpt-4o');
  });

  describe('SpotlightPlaygroundModal', () => {
    it('does not render when isPlaygroundOpen is false', () => {
      render(<SpotlightPlaygroundModal />);
      expect(screen.queryByTestId('spotlight-playground-modal')).toBeNull();
    });

    it('renders modal with sample prompts and default welcome message', () => {
      useModelSpotlightStore.getState().openPlayground(sampleSpotlight);
      render(<SpotlightPlaygroundModal />);

      expect(screen.getByTestId('spotlight-playground-modal')).toBeInTheDocument();
      expect(
        screen.getByRole('heading', { name: /GPT-6 Astra 极速试用沙箱/ })
      ).toBeInTheDocument();
      expect(screen.getByText(/1M ctx/)).toBeInTheDocument();
      expect(screen.getByText(/欢迎来到 GPT-6 Astra 极速试用沙箱/)).toBeInTheDocument();
    });

    it('submits a user prompt through the input form and receives simulated response', async () => {
      useModelSpotlightStore.getState().openPlayground(sampleSpotlight);
      render(<SpotlightPlaygroundModal />);

      const input = screen.getByPlaceholderText(/向 GPT-6 Astra 提问测试/);
      const submitBtn = screen.getByRole('button', { name: '发送测试问题' });

      fireEvent.change(input, { target: { value: '请提供高并发缓存方案' } });
      fireEvent.click(submitBtn);

      expect(screen.getByText('请提供高并发缓存方案')).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByText(/【GPT-6 Astra 实时输出】/)).toBeInTheDocument();
      });
    });

    it('clicks a sample prompt chip to execute immediately', async () => {
      useModelSpotlightStore.getState().openPlayground(sampleSpotlight);
      render(<SpotlightPlaygroundModal />);

      const firstSample = sampleSpotlight.samplePrompts[0];
      const sampleChip = screen.getByRole('button', { name: firstSample });
      fireEvent.click(sampleChip);

      // Both the sample prompt chip and the user message item should contain the text
      expect(screen.getAllByText(firstSample).length).toBe(2);

      await waitFor(() => {
        expect(screen.getByText(/首字响应: 185ms/)).toBeInTheDocument();
      });
    });

    it('clears messages and closes the playground modal', () => {
      useModelSpotlightStore.getState().openPlayground(sampleSpotlight);
      render(<SpotlightPlaygroundModal />);

      const clearBtn = screen.getByRole('button', { name: '清空临时会话' });
      fireEvent.click(clearBtn);

      expect(
        screen.queryByText(/欢迎来到 GPT-6 Astra 极速试用沙箱/)
      ).toBeNull();

      const closeBtn = screen.getByRole('button', { name: '关闭试用沙箱' });
      fireEvent.click(closeBtn);

      expect(useModelSpotlightStore.getState().isPlaygroundOpen).toBe(false);
    });

    it('switches to mount modal from within playground', () => {
      useModelSpotlightStore.getState().openPlayground(sampleSpotlight);
      render(<SpotlightPlaygroundModal />);

      const mountBtn = screen.getByRole('button', { name: '一键挂载至当前智能体' });
      fireEvent.click(mountBtn);

      expect(useModelSpotlightStore.getState().isPlaygroundOpen).toBe(false);
      expect(useModelSpotlightStore.getState().isMountModalOpen).toBe(true);
      expect(useModelSpotlightStore.getState().mountTargetSpotlight?.id).toBe(sampleSpotlight.id);
    });
  });

  describe('SpotlightMountConfirmModal', () => {
    it('does not render when isMountModalOpen is false', () => {
      render(<SpotlightMountConfirmModal />);
      expect(screen.queryByTestId('spotlight-mount-modal')).toBeNull();
    });

    it('renders comparison dashboard and handles cancellation', () => {
      useModelSpotlightStore.getState().openMountModal(sampleSpotlight);
      render(<SpotlightMountConfirmModal />);

      expect(screen.getByTestId('spotlight-mount-modal')).toBeInTheDocument();
      expect(screen.getByText('一键热挂载前沿模型')).toBeInTheDocument();
      expect(screen.getByText('openai/gpt-4o')).toBeInTheDocument();
      expect(screen.getByText('GPT-6 Astra')).toBeInTheDocument();
      expect(screen.getByText('+872K Tokens')).toBeInTheDocument();
      expect(screen.getByText(/无损热挂载保障机制/)).toBeInTheDocument();

      const cancelBtn = screen.getByRole('button', { name: '取消' });
      fireEvent.click(cancelBtn);

      expect(useModelSpotlightStore.getState().isMountModalOpen).toBe(false);
    });

    it('confirms hot-mounting, updates agent model and dispatches custom event', () => {
      const eventSpy = vi.fn();
      window.addEventListener('myrm:model-hot-mounted', eventSpy);

      useModelSpotlightStore.getState().openMountModal(sampleSpotlight);
      render(<SpotlightMountConfirmModal />);

      const confirmBtn = screen.getByRole('button', { name: '确认热挂载此模型' });
      fireEvent.click(confirmBtn);

      expect(useModelSpotlightStore.getState().isMountModalOpen).toBe(false);
      expect(useModelSpotlightStore.getState().currentAgentModelId).toBe(sampleSpotlight.modelId);
      expect(eventSpy).toHaveBeenCalledTimes(1);

      window.removeEventListener('myrm:model-hot-mounted', eventSpy);
    });
  });
});
