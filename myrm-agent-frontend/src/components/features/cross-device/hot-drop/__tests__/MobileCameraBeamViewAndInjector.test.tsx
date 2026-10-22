import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MobileCameraBeamView } from '../MobileCameraBeamView';
import { HotDropPayloadInjector } from '../HotDropPayloadInjector';
import { useCrossDeviceDropStore } from '../useCrossDeviceDropStore';
import { createMockBeamPayload } from '../beamTransportProtocol';

describe('MobileCameraBeamView & HotDropPayloadInjector', () => {
  beforeEach(() => {
    useCrossDeviceDropStore.getState().resetToDefaults();
    vi.restoreAllMocks();
  });

  describe('MobileCameraBeamView', () => {
    it('正确渲染目标桌面端设备与相机/相册触发按钮', () => {
      render(<MobileCameraBeamView />);

      expect(screen.getByTestId('mobile-camera-beam-view')).toBeInTheDocument();
      expect(screen.getByText('直连目标：Myrm 桌面端')).toBeInTheDocument();
      expect(screen.getByTestId('open-camera-btn')).toBeInTheDocument();
      expect(screen.getByTestId('open-gallery-btn')).toBeInTheDocument();
    });

    it('选择非法格式文件时能够展现校验错误提示', () => {
      render(<MobileCameraBeamView />);

      const fileInput = screen.getByTestId('camera-file-input');
      const invalidFile = new File(['dummy'], 'video.mp4', {
        type: 'video/mp4',
      });

      fireEvent.change(fileInput, { target: { files: [invalidFile] } });

      expect(screen.getByText(/不支持的文件格式/)).toBeInTheDocument();
    });

    it('模拟直接投送素材能够进入成功状态并更新 Store', async () => {
      const onCompleteMock = vi.fn();

      class MockFileReader {
        onload: ((event: { target: { result: string } }) => void) | null = null;
        readAsDataURL(): void {
          setTimeout(() => {
            if (this.onload) {
              this.onload({
                target: { result: 'data:image/jpeg;base64,mockbytes' },
              });
            }
          }, 10);
        }
      }
      vi.stubGlobal('FileReader', MockFileReader);

      render(<MobileCameraBeamView onBeamComplete={onCompleteMock} />);

      // 模拟选择合法图片并直投
      const fileInput = screen.getByTestId('camera-file-input');
      const validFile = new File(['valid-image-bytes'], 'test_sketch.jpg', {
        type: 'image/jpeg',
      });

      fireEvent.change(fileInput, { target: { files: [validFile] } });

      await waitFor(() => {
        expect(screen.getByTestId('beam-preview-container')).toBeInTheDocument();
      });
      expect(screen.getByTestId('preview-image-elem')).toBeInTheDocument();

      const submitBtn = screen.getByTestId('instant-beam-submit-btn');
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(screen.getByTestId('beam-success-card')).toBeInTheDocument();
      });

      expect(onCompleteMock).toHaveBeenCalled();
      expect(
        useCrossDeviceDropStore.getState().incomingPayloadQueue
      ).toHaveLength(1);
    });
  });

  describe('HotDropPayloadInjector', () => {
    it('无待注入素材时返回 null', () => {
      const { container } = render(<HotDropPayloadInjector />);
      expect(container.firstChild).toBeNull();
    });

    it('有待注入素材时渲染悬浮卡片并支持一键注入光标处', () => {
      const mockPayload = createMockBeamPayload(
        'iPhone 16 Pro',
        '分析白板架构'
      );
      useCrossDeviceDropStore.getState().receivePayload(mockPayload);

      render(<HotDropPayloadInjector targetInputSelector="#test-input" />);

      expect(
        screen.getByTestId('hot-drop-payload-injector')
      ).toBeInTheDocument();
      expect(screen.getByTestId('injector-thumbnail-img')).toBeInTheDocument();
      expect(screen.getByText('iPhone 16 Pro 直投')).toBeInTheDocument();
      expect(screen.getByText('“分析白板架构”')).toBeInTheDocument();

      const injectBtn = screen.getByTestId('confirm-inject-btn');
      fireEvent.click(injectBtn);

      expect(
        useCrossDeviceDropStore.getState().activeIncomingPayload
      ).toBeNull();
      expect(useCrossDeviceDropStore.getState().injectedHistory).toHaveLength(1);
    });

    it('点击忽略按钮或按 Escape 键能够关闭注入卡片', () => {
      const mockPayload = createMockBeamPayload();
      useCrossDeviceDropStore.getState().receivePayload(mockPayload);

      render(<HotDropPayloadInjector />);

      const dismissBtn = screen.getByTestId('dismiss-inject-btn');
      fireEvent.click(dismissBtn);

      expect(
        useCrossDeviceDropStore.getState().activeIncomingPayload
      ).toBeNull();
    });
  });
});
