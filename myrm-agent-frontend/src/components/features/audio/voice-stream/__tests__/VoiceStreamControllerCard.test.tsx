/**
 * Voice Stream Controller Card Component Unit Tests
 */

import React, { act } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { useVoiceStreamStore } from '../useVoiceStreamStore';
import { VoiceStreamControllerCard } from '../VoiceStreamControllerCard';

describe('VoiceStreamControllerCard', () => {
  beforeEach(() => {
    useVoiceStreamStore.getState().resetToDefault();
  });

  it('should render card with secure context badge and main duplex control button', () => {
    useVoiceStreamStore.getState().refreshEnvironmentReport({
      isSecureContext: true,
      protocol: 'https:',
      host: 'secure.myrm.ai',
      hasMediaDevices: true,
    });

    render(<VoiceStreamControllerCard />);

    expect(screen.getByTestId('voice-stream-controller-card')).toBeInTheDocument();
    expect(screen.getByTestId('badge-secure-context')).toBeInTheDocument();
    expect(screen.getByTestId('toggle-duplex-btn')).toHaveTextContent(/开启全双工对讲/);
    expect(screen.getByTestId('vad-state-silence')).toBeInTheDocument();
  });

  it('should render insecure LAN HTTP badge and expand environment guides', () => {
    useVoiceStreamStore.getState().refreshEnvironmentReport({
      isSecureContext: false,
      protocol: 'http:',
      host: '192.168.1.100:3000',
      hasMediaDevices: false,
    });

    render(<VoiceStreamControllerCard />);

    expect(screen.getByTestId('badge-insecure-context')).toBeInTheDocument();
    expect(screen.getByText(/局域网 HTTP 降级/)).toBeInTheDocument();

    // Toggle guides
    const toggleGuidesBtn = screen.getByTestId('toggle-guides-btn');
    fireEvent.click(toggleGuidesBtn);

    expect(screen.getByTestId('audio-environment-guides')).toBeInTheDocument();
    expect(screen.getByText(/运行环境指纹报告/)).toBeInTheDocument();
    expect(screen.getByText(/Tailscale/)).toBeInTheDocument();
  });

  it('should show autoplay banner when suspended and dismiss on button click', () => {
    useVoiceStreamStore.getState().refreshEnvironmentReport({
      audioContextState: 'suspended',
    });

    render(<VoiceStreamControllerCard />);

    const banner = screen.getByTestId('autoplay-banner');
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent(/检测到浏览器 Autoplay 静音拦截/);

    const resumeBtn = screen.getByTestId('resume-audio-btn');
    fireEvent.click(resumeBtn);

    expect(screen.queryByTestId('autoplay-banner')).not.toBeInTheDocument();
  });

  it('should toggle duplex stream on button click and display speech VAD state', async () => {
    useVoiceStreamStore.getState().refreshEnvironmentReport({
      isSecureContext: true,
      protocol: 'https:',
      host: 'secure.myrm.ai',
      hasMediaDevices: true,
    });

    render(<VoiceStreamControllerCard />);

    const toggleBtn = screen.getByTestId('toggle-duplex-btn');
    fireEvent.click(toggleBtn);

    // After state becomes duplex_active
    expect(useVoiceStreamStore.getState().status).toBe('duplex_active');

    // Simulate speech chunk
    act(() => {
      useVoiceStreamStore.getState().processAudioChunk(new Float32Array(50).fill(0.3));
      useVoiceStreamStore.getState().processAudioChunk(new Float32Array(50).fill(0.4));
    });

    expect(useVoiceStreamStore.getState().vadState).toBe('speech');
  });

  it('should display error output when store has error message', () => {
    useVoiceStreamStore.setState({
      errorMessage: '测试麦克风硬件故障',
    });

    render(<VoiceStreamControllerCard />);
    expect(screen.getByTestId('voice-stream-error-output')).toBeInTheDocument();
    expect(screen.getByText('测试麦克风硬件故障')).toBeInTheDocument();
  });
});
