/**
 * [INPUT]
 * - @/lib/desktop-bridge::desktopBridge (POS: 桌面桥接单例，按运行环境选择 Tauri 或 Web 降级实现)
 * - @/lib/desktop-bridge::installExternalLinkPolicy (POS: 把新窗口 http(s) 的 window.open 路由到系统浏览器)
 * - @/lib/tauri::isTauriEnvironment (POS: Tauri 原生桥接层环境探测)
 *
 * [OUTPUT]
 * - ExternalLinkInitializer: Tauri 桌面端挂载期间安装外链策略，卸载时还原 window.open；不渲染任何内容
 *
 * [POS]
 * 根布局级副作用组件，与 DeepLinkListener 同级 eager 挂载；非 Tauri 环境不改动 window.open，浏览器保留自身的弹窗处理。
 */
'use client';

import { useEffect } from 'react';

import { desktopBridge, installExternalLinkPolicy } from '@/lib/desktop-bridge';
import { isTauriEnvironment } from '@/lib/tauri';

export default function ExternalLinkInitializer() {
  useEffect(() => {
    if (!isTauriEnvironment()) {
      return undefined;
    }
    return installExternalLinkPolicy(window, (url) => desktopBridge.shell.openExternalUrl(url));
  }, []);

  return null;
}
