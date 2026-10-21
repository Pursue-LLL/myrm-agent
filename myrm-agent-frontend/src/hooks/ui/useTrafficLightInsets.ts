/**
 * [INPUT]
 * - @/lib/desktop-bridge::desktopBridge
 *
 * [OUTPUT]
 * - useTrafficLightInsets: 自适应计算 macOS 桌面端交通灯安全区留白 Hook
 *
 * [POS]
 * UI 平台安全区自适应层。在 macOS Tauri 沉浸式桌面端自动为顶部预留红绿灯安全留白，
 * 在 Windows、Linux 及纯 Web 端保持 0px，防止导航或侧边栏控件被遮挡。
 */

'use client';

import { useEffect, useState } from 'react';
import { desktopBridge } from '@/lib/desktop-bridge';

export interface TrafficLightInsets {
  /** 顶部预留安全距离（px） */
  topInset: number;
  /** 左侧预留安全距离（px） */
  leftInset: number;
  /** 是否处于 macOS 原生沉浸式桌面环境 */
  isImmersiveMac: boolean;
}

export function useTrafficLightInsets(): TrafficLightInsets {
  const [insets, setInsets] = useState<TrafficLightInsets>(() => {
    const controls = desktopBridge.getWindowControlsState();
    return {
      topInset: controls.controlsInsetTop,
      leftInset: controls.controlsInsetLeft,
      isImmersiveMac: controls.platform === 'macos' && controls.isDesktop,
    };
  });

  useEffect(() => {
    const controls = desktopBridge.getWindowControlsState();
    const isImmersiveMac = controls.platform === 'macos' && controls.isDesktop;

    setInsets({
      topInset: controls.controlsInsetTop,
      leftInset: controls.controlsInsetLeft,
      isImmersiveMac,
    });

    if (typeof document !== 'undefined') {
      document.documentElement.style.setProperty('--traffic-light-inset-top', `${controls.controlsInsetTop}px`);
      document.documentElement.style.setProperty('--traffic-light-inset-left', `${controls.controlsInsetLeft}px`);
    }
  }, []);

  return insets;
}
