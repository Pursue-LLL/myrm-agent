import { SynthAudioConfig } from './skeuomorphicTypes';

class SkeuomorphicAudioEngine {
  private audioCtx: AudioContext | null = null;
  private config: SynthAudioConfig = {
    soundEnabled: true,
    volume: 0.3,
    hapticEnabled: true,
  };

  private getAudioContext(): AudioContext | null {
    if (typeof window === 'undefined') {
      return null;
    }
    const AudioContextClass =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextClass) {
      return null;
    }
    if (!this.audioCtx) {
      try {
        this.audioCtx = new AudioContextClass();
      } catch {
        return null;
      }
    }
    if (this.audioCtx && this.audioCtx.state === 'suspended') {
      this.audioCtx.resume().catch(() => {});
    }
    return this.audioCtx;
  }

  public updateConfig(partial: Partial<SynthAudioConfig>): void {
    this.config = {
      ...this.config,
      ...partial,
    };
  }

  public getConfig(): SynthAudioConfig {
    return { ...this.config };
  }

  public playRatchetClick(): void {
    if (!this.config.soundEnabled) {
      return;
    }
    const ctx = this.getAudioContext();
    if (!ctx) {
      this.triggerHapticPulse(8);
      return;
    }

    try {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      const filter = ctx.createBiquadFilter();

      filter.type = 'bandpass';
      filter.frequency.setValueAtTime(2400, ctx.currentTime);
      filter.Q.setValueAtTime(8, ctx.currentTime);

      osc.type = 'triangle';
      osc.frequency.setValueAtTime(1200, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(300, ctx.currentTime + 0.012);

      const effectiveVolume = Math.max(0.01, Math.min(1, this.config.volume));
      gain.gain.setValueAtTime(effectiveVolume * 0.4, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.012);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(ctx.destination);

      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.015);

      this.triggerHapticPulse(10);
    } catch {
      // 安全静默降级
    }
  }

  public playLcdConfirmBeep(): void {
    if (!this.config.soundEnabled) {
      return;
    }
    const ctx = this.getAudioContext();
    if (!ctx) {
      this.triggerHapticPulse(25);
      return;
    }

    try {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.setValueAtTime(1760, ctx.currentTime + 0.03);

      const effectiveVolume = Math.max(0.01, Math.min(1, this.config.volume));
      gain.gain.setValueAtTime(effectiveVolume * 0.5, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.08);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.09);

      this.triggerHapticPulse(30);
    } catch {
      // 安全静默降级
    }
  }

  public playPolaroidShutter(): void {
    if (!this.config.soundEnabled) {
      return;
    }
    const ctx = this.getAudioContext();
    if (!ctx) {
      this.triggerHapticPulse(40);
      return;
    }

    try {
      const bufferSize = Math.floor(ctx.sampleRate * 0.08);
      const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
      const output = buffer.getChannelData(0);
      for (let i = 0; i < bufferSize; i++) {
        output[i] = Math.random() * 2 - 1;
      }

      const whiteNoise = ctx.createBufferSource();
      whiteNoise.buffer = buffer;

      const filter = ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(1200, ctx.currentTime);

      const gain = ctx.createGain();
      const effectiveVolume = Math.max(0.01, Math.min(1, this.config.volume));
      gain.gain.setValueAtTime(effectiveVolume * 0.6, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.08);

      whiteNoise.connect(filter);
      filter.connect(gain);
      gain.connect(ctx.destination);

      whiteNoise.start(ctx.currentTime);
      whiteNoise.stop(ctx.currentTime + 0.09);

      this.triggerHapticPulse(45);
    } catch {
      // 安全静默降级
    }
  }

  public triggerHapticPulse(ms = 15): void {
    if (!this.config.hapticEnabled) {
      return;
    }
    if (typeof window !== 'undefined' && typeof window.navigator !== 'undefined' && 'vibrate' in window.navigator) {
      try {
        window.navigator.vibrate(ms);
      } catch {
        // 忽略不支持平台
      }
    }
  }
}

export const skeuomorphicAudioEngine = new SkeuomorphicAudioEngine();
