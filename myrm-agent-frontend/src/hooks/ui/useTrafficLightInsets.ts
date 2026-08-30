/**
 * [INPUT]
 * - @/lib/desktopBridge::useDesktopBridge
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
import { desktopBridge } from '@/lib/desktopBridge';

export interface TrafficLightInsets {
  /** 顶部预留安全距离（px） */
  topInset: number;
  /** 左侧预留安全距离（px） */
  leftInset: number;
  /** 是否处于 macOS 原生沉浸式桌面环境 */
  isImmersiveMac: boolean;
}

const MAC_DEFAULT_TOP_INSET = 28;
const MAC_DEFAULT_LEFT_INSET = 78;

export function useTrafficLightInsets(): TrafficLightInsets {
  const [insets, setInsets] = useState<TrafficLightInsets>({
    topInset: 0,
    leftInset: 0,
    isImmersiveMac: false,
  });

  useEffect(() => {
    const isMac = desktopBridge.isMacOS();
    const isDesk = desktopBridge.isDesktop();

    if (isMac && isDesk) {
      setInsets({
        topInset: MAC_DEFAULT_TOP_INSET,
        leftInset: MAC_DEFAULT_LEFT_INSET,
        isImmersiveMac: true,
      });

      if (typeof document !== 'undefined') {
        document.documentElement.style.setProperty('--traffic-light-inset-top', `${MAC_DEFAULT_TOP_INSET}px`);
        document.documentElement.style.setProperty('--traffic-light-inset-left', `${MAC_DEFAULT_LEFT_INSET}px`);
      }
    } else {
      setInsets({
        topInset: 0,
        leftInset: 0,
        isImmersiveMac: false,
      });

      if (typeof document !== 'undefined') {
        document.documentElement.style.setProperty('--traffic-light-inset-top', '0px');
        document.documentElement.style.setProperty('--traffic-light-inset-left', '0px');
      }
    }
  }, []);

  return insets;
}
