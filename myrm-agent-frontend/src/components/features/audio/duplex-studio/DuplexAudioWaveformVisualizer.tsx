import React from 'react';
import { Mic, Volume2 } from 'lucide-react';
import { AudioChannelMetrics, DuplexSessionStatus } from './duplexVoiceTypes';
import { normalizeWaveformHeights } from './duplexVoiceEngine';

export interface DuplexAudioWaveformVisualizerProps {
  status: DuplexSessionStatus;
  metrics: AudioChannelMetrics;
  className?: string;
}

export const DuplexAudioWaveformVisualizer: React.FC<
  DuplexAudioWaveformVisualizerProps
> = ({ status, metrics, className = '' }) => {
  const isAgentSpeaking = status === 'speaking';
  const isUserSpeaking = metrics.vadActive && status !== 'idle';

  const micHeights = normalizeWaveformHeights(metrics.micVolume, 10);
  const agentHeights = normalizeWaveformHeights(metrics.agentVolume, 10);

  return (
    <div
      data-testid="duplex-audio-waveform-visualizer"
      className={`p-3 rounded-2xl bg-zinc-950/80 border border-zinc-800 backdrop-blur-md space-y-2.5 font-sans ${className}`}
    >
      {/* 1. 用户麦克风流波形通道 */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-[11px] font-mono text-zinc-400">
          <span className="flex items-center gap-1.5">
            <Mic
              className={`w-3.5 h-3.5 ${
                isUserSpeaking ? 'text-indigo-400 animate-pulse' : 'text-zinc-500'
              }`}
            />
            <span>麦克风收音 (VAD)</span>
          </span>
          <span className="text-[10px] text-zinc-500">
            {metrics.micVolume}% · {metrics.noiseFloorDb}dB
          </span>
        </div>

        <div
          data-testid="mic-waveform-bars"
          className="flex items-center justify-center gap-1 h-8 px-2 rounded-xl bg-zinc-900/60 border border-zinc-850"
        >
          {micHeights.map((h, i) => (
            <div
              key={`mic-${i}`}
              className={`w-1.5 rounded-full transition-all duration-75 ${
                isUserSpeaking
                  ? 'bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.5)]'
                  : 'bg-zinc-700 opacity-30'
              }`}
              style={{ height: `${h}%` }}
            />
          ))}
        </div>
      </div>

      {/* 2. 智能体 TTS 播报波形通道 */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-[11px] font-mono text-zinc-400">
          <span className="flex items-center gap-1.5">
            <Volume2
              className={`w-3.5 h-3.5 ${
                isAgentSpeaking
                  ? 'text-emerald-400 animate-pulse'
                  : 'text-zinc-500'
              }`}
            />
            <span>智能体语音流 (TTS)</span>
          </span>
          <span className="text-[10px] text-zinc-500">
            {isAgentSpeaking ? `${Math.round(metrics.agentVolume)}%` : '静音待命'}
          </span>
        </div>

        <div
          data-testid="agent-waveform-bars"
          className="flex items-center justify-center gap-1 h-8 px-2 rounded-xl bg-zinc-900/60 border border-zinc-850"
        >
          {agentHeights.map((h, i) => (
            <div
              key={`agent-${i}`}
              className={`w-1.5 rounded-full transition-all duration-75 ${
                isAgentSpeaking
                  ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]'
                  : 'bg-zinc-700 opacity-30'
              }`}
              style={{ height: `${isAgentSpeaking ? h : 15}%` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
};
