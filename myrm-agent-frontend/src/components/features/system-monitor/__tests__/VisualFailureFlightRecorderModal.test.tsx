import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { VisualFailureFlightRecorderModal } from '../VisualFailureFlightRecorderModal';
import { VisualFailureSliceItem } from '../visualFlightRecorderTypes';

describe('VisualFailureFlightRecorderModal Component', () => {
  const mockSlices: VisualFailureSliceItem[] = [
    {
      slice_id: 'vslice-popup-101',
      trace_id: 'tr-checkout-fail',
      session_id: 'sess-buyer-9',
      failure_kind: 'popup_overlay',
      root_cause_label: 'Unexpected promotion banner blocked primary submit button',
      total_frames: 3,
      duration_seconds: 0.6,
      frames: [
        {
          frame_index: 0,
          timestamp_ms: 1719000000000,
          image_data_uri: 'data:image/png;base64,frame_0',
          dom_event_summary: 'DOM: user click on checkout button',
        },
        {
          frame_index: 1,
          timestamp_ms: 1719000000200,
          image_data_uri: 'data:image/png;base64,frame_1',
          dom_event_summary: 'DOM: modal popup rendered over main viewport',
        },
        {
          frame_index: 2,
          timestamp_ms: 1719000000400,
          image_data_uri: 'data:image/png;base64,frame_2',
          dom_event_summary: 'DOM: click intercepted by overlay mask',
        },
      ],
      created_at_ms: 1719000000500,
    },
    {
      slice_id: 'vslice-captcha-202',
      trace_id: 'tr-login-fail',
      session_id: 'sess-auth-1',
      failure_kind: 'captcha_slider',
      root_cause_label: 'Geetest slider captcha blocked automated progression',
      total_frames: 1,
      duration_seconds: 0.2,
      frames: [
        {
          frame_index: 0,
          timestamp_ms: 1719000001000,
          image_data_uri: 'data:image/png;base64,captcha_screen',
          dom_event_summary: 'DOM: slider puzzle appeared',
        },
      ],
      created_at_ms: 1719000001200,
    },
  ];

  it('renders modal with root-cause diagnostic banner and frames HUD when open', () => {
    render(
      <VisualFailureFlightRecorderModal
        isOpen={true}
        onClose={vi.fn()}
        slices={mockSlices}
      />
    );

    expect(screen.getByText('智能体视觉故障黑匣子与卡顿回放')).toBeInTheDocument();
    expect(screen.getByText('已捕获故障切片 (2)')).toBeInTheDocument();
    expect(screen.getByText('视觉排障定论:')).toBeInTheDocument();

    const popupBadges = screen.getAllByText('popup_overlay');
    expect(popupBadges.length).toBeGreaterThanOrEqual(1);

    const labels = screen.getAllByText('Unexpected promotion banner blocked primary submit button');
    expect(labels.length).toBeGreaterThanOrEqual(1);

    expect(screen.getByText('逐帧定位胶卷 (Filmstrip Reel)')).toBeInTheDocument();
  });

  it('toggles play/pause state when clicking play button', async () => {
    render(
      <VisualFailureFlightRecorderModal
        isOpen={true}
        onClose={vi.fn()}
        slices={mockSlices}
      />
    );

    const pauseBtn = screen.getByText('暂停');
    await React.act(async () => {
      fireEvent.click(pauseBtn);
    });

    expect(screen.getByText('播放')).toBeInTheDocument();
  });

  it('switches slice when clicking a different slice in list', async () => {
    const handleSelect = vi.fn();
    render(
      <VisualFailureFlightRecorderModal
        isOpen={true}
        onClose={vi.fn()}
        slices={mockSlices}
        onSelectSlice={handleSelect}
      />
    );

    const captchaCard = screen.getByText('Geetest slider captcha blocked automated progression');
    await React.act(async () => {
      fireEvent.click(captchaCard);
    });

    expect(handleSelect).toHaveBeenCalledWith('vslice-captcha-202');
  });

  it('calls onClose when clicking close button', async () => {
    const handleClose = vi.fn();
    render(
      <VisualFailureFlightRecorderModal
        isOpen={true}
        onClose={handleClose}
        slices={mockSlices}
      />
    );

    const closeBtn = screen.getByRole('button', { name: '关闭' });
    await React.act(async () => {
      fireEvent.click(closeBtn);
    });

    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
