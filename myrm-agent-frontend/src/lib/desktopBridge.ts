/**
 * [INPUT]
 * - @/lib/tauri (POS: isTauriEnvironment)
 * - @tauri-apps/api/* (POS: 桌面端窗口与应用 API)
 * - @tauri-apps/plugin-shell (POS: 桌面端系统外链与文件唤起)
 * - @tauri-apps/plugin-dialog (POS: 原生文件与文件夹选择器)
 * - @tauri-apps/plugin-notification (POS: 原生桌面系统通知)
 *
 * [OUTPUT]
 * - desktopBridge: 统一桌面原生桥接门面
 * - type DesktopBridgeInterface: 桌面桥接强类型接口
 * - type FileFilterOption: 文件选择过滤项契约
 * - useDesktopBridge: React Hook 便捷访问
 *
 * [POS]
 * 桌面与 Web 统一桥接契约层。收敛所有桌面端原生系统能力调用，
 * 为非桌面环境（纯 WebUI / Cloud 沙箱）提供类型安全、无副作用的优雅降级实现。
 */

import { isTauriEnvironment } from '@/lib/tauri';

export interface FileFilterOption {
  name: string;
  extensions: string[];
}

export interface DirectoryPickerOptions {
  title?: string;
  defaultPath?: string;
}

export interface FilePickerOptions {
  title?: string;
  defaultPath?: string;
  multiple?: boolean;
  filters?: FileFilterOption[];
}

export interface NotificationOptions {
  title: string;
  body: string;
}

export interface DesktopBridgeInterface {
  /** 判断当前是否运行在桌面端原生环境 */
  isDesktop: () => boolean;
  /** 判断当前宿主是否为 macOS */
  isMacOS: () => boolean;
  /** 判断当前宿主是否为 Windows */
  isWindows: () => boolean;
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
  /** 唤起系统原生目录选择器（非桌面环境优雅返回 null） */
  openDirectoryPicker: (options?: DirectoryPickerOptions) => Promise<string | null>;
  /** 唤起系统原生文件选择器（非桌面环境优雅返回 null） */
  openFilePicker: (options?: FilePickerOptions) => Promise<string | string[] | null>;
  /** 发送系统桌面级通知（支持 Web Notification 降级） */
  sendNotification: (options: NotificationOptions) => Promise<boolean>;
  /** 请求用户注意力（macOS Dock 弹跳 / Windows 任务栏闪烁） */
  requestUserAttention: (level?: 'critical' | 'informational') => Promise<void>;
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

  public isWindows(): boolean {
    if (typeof navigator === 'undefined') {
      return false;
    }
    return /(Windows|Win32|Win64)/i.test(navigator.userAgent);
  }

  public async showItemInFolder(path: string): Promise<boolean> {
    if (!path || !this.isDesktop()) {
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

  public async openDirectoryPicker(options?: DirectoryPickerOptions): Promise<string | null> {
    if (!this.isDesktop()) {
      return null;
    }

    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({
        directory: true,
        multiple: false,
        title: options?.title,
        defaultPath: options?.defaultPath,
      });

      if (typeof selected === 'string' && selected.trim()) {
        return selected;
      }
      return null;
    } catch {
      return null;
    }
  }

  public async openFilePicker(options?: FilePickerOptions): Promise<string | string[] | null> {
    if (!this.isDesktop()) {
      return null;
    }

    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({
        directory: false,
        multiple: options?.multiple ?? false,
        title: options?.title,
        defaultPath: options?.defaultPath,
        filters: options?.filters,
      });

      return selected;
    } catch {
      return null;
    }
  }

  public async sendNotification(options: NotificationOptions): Promise<boolean> {
    if (this.isDesktop()) {
      try {
        const { isPermissionGranted, requestPermission, sendNotification } =
          await import('@tauri-apps/plugin-notification');
        let permitted = await isPermissionGranted();
        if (!permitted) {
          const perm = await requestPermission();
          permitted = perm === 'granted';
        }
        if (permitted) {
          sendNotification({
            title: options.title,
            body: options.body,
          });
          return true;
        }
      } catch {
        // Fall through to browser notification fallback
      }
    }

    if (typeof window !== 'undefined' && 'Notification' in window) {
      try {
        if (Notification.permission === 'granted') {
          new Notification(options.title, { body: options.body });
          return true;
        }
        if (Notification.permission !== 'denied') {
          const perm = await Notification.requestPermission();
          if (perm === 'granted') {
            new Notification(options.title, { body: options.body });
            return true;
          }
        }
      } catch {
        // Notification failed or blocked
      }
    }

    return false;
  }

  public async requestUserAttention(level: 'critical' | 'informational' = 'informational'): Promise<void> {
    if (!this.isDesktop()) {
      return;
    }

    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      // 1 = Informational, 2 = Critical (UserAttentionType in Tauri)
      const attentionType = level === 'critical' ? 2 : 1;
      await getCurrentWindow().requestUserAttention(attentionType);
    } catch {
      // Graceful fallback
    }
  }
}

export const desktopBridge: DesktopBridgeInterface = new DesktopBridgeImpl();

export function useDesktopBridge(): DesktopBridgeInterface {
  return desktopBridge;
}
