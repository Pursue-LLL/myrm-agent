import { describe, it, expect, beforeEach } from 'vitest';
import { useBidiShieldStore } from '../useBidiShieldStore';

describe('useBidiShieldStore', () => {
  beforeEach(() => {
    useBidiShieldStore.getState().resetToDefault();
  });

  it('初始状态具备默认方向、Windows 字体加固开启与预设样本', () => {
    const state = useBidiShieldStore.getState();
    expect(state.direction).toBe('auto');
    expect(state.isWindowsTypographyShieldActive).toBe(true);
    expect(state.autoDetectTextDirection).toBe(true);
    expect(state.samplePresets.length).toBeGreaterThanOrEqual(3);
  });

  it('setDirection 能够更新书写方向模式', () => {
    const { setDirection } = useBidiShieldStore.getState();
    setDirection('rtl');
    expect(useBidiShieldStore.getState().direction).toBe('rtl');

    setDirection('ltr');
    expect(useBidiShieldStore.getState().direction).toBe('ltr');
  });

  it('setActiveLocale 根据语系特征自适应更新方向', () => {
    const { setActiveLocale } = useBidiShieldStore.getState();

    setActiveLocale('he');
    expect(useBidiShieldStore.getState().activeLocale).toBe('he');
    expect(useBidiShieldStore.getState().direction).toBe('rtl');

    setActiveLocale('zh-CN');
    expect(useBidiShieldStore.getState().activeLocale).toBe('zh-CN');
    expect(useBidiShieldStore.getState().direction).toBe('ltr');
  });

  it('toggleWindowsTypographyShield 能够翻转 Windows 字体防护状态', () => {
    const { toggleWindowsTypographyShield } = useBidiShieldStore.getState();
    expect(useBidiShieldStore.getState().isWindowsTypographyShieldActive).toBe(true);

    toggleWindowsTypographyShield();
    expect(useBidiShieldStore.getState().isWindowsTypographyShieldActive).toBe(false);

    toggleWindowsTypographyShield();
    expect(useBidiShieldStore.getState().isWindowsTypographyShieldActive).toBe(true);
  });

  it('loadPreset 能够加载预设样本并更新输入文本与期望方向', () => {
    const { loadPreset } = useBidiShieldStore.getState();
    loadPreset('preset-zh-tech');

    const state = useBidiShieldStore.getState();
    expect(state.direction).toBe('ltr');
    expect(state.customInputText).toContain('padding-inline-start');
  });

  it('getCurrentDetection 返回当前输入文本的实时双向探测结果', () => {
    const { setCustomInputText, getCurrentDetection } = useBidiShieldStore.getState();
    setCustomInputText('مرحبا بالعالم');

    const detection = getCurrentDetection();
    expect(detection.dominantDirection).toBe('rtl');
    expect(detection.containsRtl).toBe(true);
  });
});
