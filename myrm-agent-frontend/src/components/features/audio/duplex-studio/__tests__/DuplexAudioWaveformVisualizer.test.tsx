import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DuplexAudioWaveformVisualizer } from '../DuplexAudioWaveformVisualizer';
import { AudioChannelMetrics } from '../duplexVoiceTypes';

describe('DuplexAudioWaveformVisualizer', () => {
  const baseMetrics: AudioChannelMetrics = {
    micVolume: 0,
    agentVolume: 0,
    noiseFloorDb: -50,
    vadActive: false,
  };

  it('正确渲染麦克风与智能体两条音频通道及待命文本', () => {
    render(
      <DuplexAudioWaveformVisualizer status="idle" metrics={baseMetrics} />
    );

    expect(
      screen.getByTestId('duplex-audio-waveform-visualizer')
    ).toBeInTheDocument();
    expect(screen.getByText('麦克风收音 (VAD)')).toBeInTheDocument();
    expect(screen.getByText('智能体语音流 (TTS)')).toBeInTheDocument();
    expect(screen.getByText('静音待命')).toBeInTheDocument();
  });

  it('当麦克风检测到用户说话时呈现激活波形', () => {
    const activeUserMetrics: AudioChannelMetrics = {
      micVolume: 65,
      agentVolume: 0,
      noiseFloorDb: -42,
      vadActive: true,
    };

    render(
      <DuplexAudioWaveformVisualizer
        status="listening"
        metrics={activeUserMetrics}
      />
    );

    expect(screen.getByText(/65%/)).toBeInTheDocument();
    const micBarsContainer = screen.getByTestId('mic-waveform-bars');
    expect(micBarsContainer.children.length).toBe(10);
  });

  it('当智能体处于 speaking 状态时呈现播报音量与动态柱状波形', () => {
    const activeAgentMetrics: AudioChannelMetrics = {
      micVolume: 10,
      agentVolume: 72,
      noiseFloorDb: -48,
      vadActive: false,
    };

    render(
      <DuplexAudioWaveformVisualizer
        status="speaking"
        metrics={activeAgentMetrics}
      />
    );

    expect(screen.getByText('72%')).toBeInTheDocument();
    const agentBarsContainer = screen.getByTestId('agent-waveform-bars');
    expect(agentBarsContainer.children.length).toBe(10);
  });
});
