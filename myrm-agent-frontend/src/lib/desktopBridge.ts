/**
 * [INPUT]
 * - @/lib/tauri (POS: isTauriEnvironment, invokeTauriCommand)
 * - @tauri-apps/api/* (POS: 桌面端窗口与应用 API)
 * - @tauri-apps/plugin-shell (POS: 桌面端系统外链与文件唤起)
 *
 * [OUTPUT]
 * - desktopBridge: 统一桌面原生桥接门面
 * - type DesktopBridgeInterface: 桌面桥接强类型接口
 * - useDesktopBridge: React Hook 便捷访问
 *
 * [POS]
 * 桌面与 Web 统一桥接契约层。收敛所有桌面端原生系统能力调用，
 * 为非桌面环境（纯 WebUI / Cloud 沙箱）提供类型安全、无副作用的优雅降级实现。
 */

import { isTauriEnvironment } from '@/lib/tauri';

export interface DesktopBridgeInterface {
  /** 判断当前是否运行在桌面端原生环境 */
  isDesktop: () => boolean;
  /** 判断当前宿主是否为 macOS 桌面端 */
  isMacOS: () => boolean;
  /** 在系统默认文件管理器中定位并高亮显示指定文件/目录 */
  showItemInFolder: (path: string) => Promise<boolean>;
  /** 使用系统默认浏览器打开外部超链接 */
  openExternal: (url: string) => Promise<boolean>;
  /** 最小化桌面主窗口 */
  minimizeWindow: () => Promise<void>;
  /** 切换桌面主窗口最大化/还原状态 */
  toggleMaximizeWindow: () => Promise<void>;
  /** 关闭桌面主窗口（按配置退回托盘或退出） */
  closeWindow: () => Promise<void>;
  /** 获取桌面宿主应用版本号 */
  getAppVersion: () => Promise<string>;
  /** 安全写入系统剪贴板 */
  writeClipboard: (text: string) => Promise<boolean>;
}

class DesktopBridgeImpl implements DesktopBridgeInterface {
  public isDesktop(): boolean {
    return isTauriEnvironment();
  }

  public isMacOS(): boolean {
    if (typeof navigator === 'undefined') {
      return false;
    }
    return /(Macintosh|Mac OS X)/i.test(navigator.userAgent);
  }

  public async showItemInFolder(path: string): Promise<boolean> {
    if (!this.isDesktop()) {
      return false;
    }

    try {
      const { open } = await import('@tauri-apps/plugin-shell');
      await open(path);
      return true;
    } catch {
      return false;
    }
  }

  public async openExternal(url: string): Promise<boolean> {
    if (!url) {
      return false;
    }

    if (this.isDesktop()) {
      try {
        const { open } = await import('@tauri-apps/plugin-shell');
        await open(url);
        return true;
      } catch {
        // Fallback to standard window.open below
      }
    }

    if (typeof window !== 'undefined') {
      window.open(url, '_blank', 'noopener,noreferrer');
      return true;
    }

    return false;
  }

  public async minimizeWindow(): Promise<void> {
    if (!this.isDesktop()) {
      return;
    }

    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      await getCurrentWindow().minimize();
    } catch {
      // Graceful fallback for non-tauri or mock environments
    }
  }

  public async toggleMaximizeWindow(): Promise<void> {
    if (!this.isDesktop()) {
      return;
    }

    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      await getCurrentWindow().toggleMaximize();
    } catch {
      // Graceful fallback
    }
  }

  public async closeWindow(): Promise<void> {
    if (!this.isDesktop()) {
      return;
    }

    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      await getCurrentWindow().close();
    } catch {
      // Graceful fallback
    }
  }

  public async getAppVersion(): Promise<string> {
    if (!this.isDesktop()) {
      return process.env.NEXT_PUBLIC_APP_VERSION || '0.1.0';
    }

    try {
      const { getVersion } = await import('@tauri-apps/api/app');
      return await getVersion();
    } catch {
      return process.env.NEXT_PUBLIC_APP_VERSION || '0.1.0';
    }
  }

  public async writeClipboard(text: string): Promise<boolean> {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch {
        // Continue to fallback
      }
    }
    return false;
  }
}

export const desktopBridge: DesktopBridgeInterface = new DesktopBridgeImpl();

export function useDesktopBridge(): DesktopBridgeInterface {
  return desktopBridge;
}
