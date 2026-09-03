/**
 * [INPUT]
 * - @/lib/tauri (POS: isTauriEnvironment)
 * - @/lib/desktop-bridge (POS: 统一桌面原生与 Web 降级契约体系)
 *
 * [OUTPUT]
 * - desktopBridge: 统一桌面原生桥接门面（兼容平滑迁移）
 * - type DesktopBridgeInterface: 桌面桥接强类型接口
 * - type FileFilterOption, DirectoryPickerOptions, FilePickerOptions, NotificationOptions
 * - useDesktopBridge: React Hook 便捷访问
 *
 * [POS]
 * 桌面与 Web 统一桥接门面层。收敛所有桌面端原生系统能力调用，
 * 并与 @/lib/desktop-bridge 体系深度融合，为纯 WebUI / Tauri 桌面端 / Cloud 沙箱提供 100% 同构支持。
 */

import { isTauriEnvironment } from '@/lib/tauri';
import { desktopBridge as coreDesktopBridge, type IDesktopBridge } from '@/lib/desktop-bridge';

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
  private readonly core: IDesktopBridge;

  constructor(core: IDesktopBridge = coreDesktopBridge) {
    this.core = core;
  }

  public isDesktop(): boolean {
    return isTauriEnvironment() || this.core.isDesktop;
  }

  public isMacOS(): boolean {
    if (typeof navigator === 'undefined') {
      return false;
    }
    return /(Macintosh|Mac OS X)/i.test(navigator.userAgent) || this.core.platform === 'macos';
  }

  public isWindows(): boolean {
    if (typeof navigator === 'undefined') {
      return false;
    }
    return /(Windows|Win32|Win64)/i.test(navigator.userAgent) || this.core.platform === 'windows';
  }

  public async showItemInFolder(path: string): Promise<boolean> {
    if (!path) return false;
    if (this.isDesktop()) {
      return await this.core.shell.showInFileManager(path);
    }
    return false;
  }

  public async openExternal(url: string): Promise<boolean> {
    if (!url) return false;
    return await this.core.shell.openExternalUrl(url);
  }

  public async minimizeWindow(): Promise<void> {
    await this.core.window.minimize();
  }

  public async toggleMaximizeWindow(): Promise<void> {
    await this.core.window.toggleMaximize();
  }

  public async closeWindow(): Promise<void> {
    await this.core.window.close();
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

    const res = await this.core.shell.openFileDialog({
      directory: true,
      multiple: false,
      title: options?.title,
      defaultPath: options?.defaultPath,
    });

    if (typeof res === 'string' && res.trim()) {
      return res;
    }
    if (Array.isArray(res) && res.length > 0 && typeof res[0] === 'string') {
      return res[0];
    }
    return null;
  }

  public async openFilePicker(options?: FilePickerOptions): Promise<string | string[] | null> {
    if (!this.isDesktop()) {
      return null;
    }

    return await this.core.shell.openFileDialog({
      directory: false,
      multiple: options?.multiple ?? false,
      title: options?.title,
      defaultPath: options?.defaultPath,
      filters: options?.filters,
    });
  }

  public async sendNotification(options: NotificationOptions): Promise<boolean> {
    return await this.core.notification.show({
      title: options.title,
      body: options.body,
    });
  }

  public async requestUserAttention(level: 'critical' | 'informational' = 'informational'): Promise<void> {
    if (!this.isDesktop()) {
      return;
    }

    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
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
