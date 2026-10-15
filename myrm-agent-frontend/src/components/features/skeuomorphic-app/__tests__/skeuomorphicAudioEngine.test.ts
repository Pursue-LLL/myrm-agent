import { describe, it, expect, vi, beforeEach } from 'vitest';
import { skeuomorphicAudioEngine } from '../skeuomorphicAudioEngine';

describe('skeuomorphicAudioEngine', () => {
  beforeEach(() => {
    skeuomorphicAudioEngine.updateConfig({
      soundEnabled: true,
      volume: 0.3,
      hapticEnabled: true,
    });
  });

  it('updateConfig 与 getConfig 应正确管理音效及震动配置', () => {
    skeuomorphicAudioEngine.updateConfig({ soundEnabled: false, volume: 0.5 });
    const config = skeuomorphicAudioEngine.getConfig();
    expect(config.soundEnabled).toBe(false);
    expect(config.volume).toBe(0.5);
    expect(config.hapticEnabled).toBe(true);
  });

  it('在无真实 Web Audio 环境或禁用声音时播放音效应安全静默降级不崩溃', () => {
    expect(() => {
      skeuomorphicAudioEngine.playRatchetClick();
      skeuomorphicAudioEngine.playLcdConfirmBeep();
      skeuomorphicAudioEngine.playPolaroidShutter();
    }).not.toThrow();

    skeuomorphicAudioEngine.updateConfig({ soundEnabled: false });
    expect(() => {
      skeuomorphicAudioEngine.playRatchetClick();
      skeuomorphicAudioEngine.playLcdConfirmBeep();
      skeuomorphicAudioEngine.playPolaroidShutter();
    }).not.toThrow();
  });

  it('triggerHapticPulse 在支持 navigator.vibrate 时应正确调用', () => {
    const vibrateMock = vi.fn();
    Object.defineProperty(window.navigator, 'vibrate', {
      value: vibrateMock,
      writable: true,
      configurable: true,
    });

    skeuomorphicAudioEngine.triggerHapticPulse(20);
    expect(vibrateMock).toHaveBeenCalledWith(20);

    skeuomorphicAudioEngine.updateConfig({ hapticEnabled: false });
    vibrateMock.mockClear();
    skeuomorphicAudioEngine.triggerHapticPulse(20);
    expect(vibrateMock).not.toHaveBeenCalled();
  });
});
