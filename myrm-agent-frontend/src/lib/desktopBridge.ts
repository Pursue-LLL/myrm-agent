/**
 * [INPUT]
 * - @/lib/tauri (POS: isTauriEnvironment)
 * - @/lib/desktop-bridge (POS: 统一桌面原生与 Web 降级契约体系)
 *
 * [OUTPUT]
 * - desktopBridge: 应用层桌面能力门面（平台判断、外链、目录选择）
 * - type DesktopBridgeInterface: 桌面桥接强类型接口
 * - type DirectoryPickerOptions
 *
 * [POS]
 * 桌面与 Web 统一桥接门面层。业务代码经此调用桌面端原生能力，
 * 纯 WebUI / Cloud 沙箱下平台判断为否、目录选择返回 null，外链走浏览器标准 API。
 */

import { detectDesktopPlatform } from '@/lib/desktop-bridge/platform-detection';
import { desktopBridge as coreDesktopBridge, type IDesktopBridge } from '@/lib/desktop-bridge';
import { isTauriEnvironment } from '@/lib/tauri';

export interface DirectoryPickerOptions {
  title?: string;
  defaultPath?: string;
}

export interface DesktopBridgeInterface {
  /** 判断当前是否运行在桌面端原生环境 */
  isDesktop: () => boolean;
  /** 判断当前宿主是否为 macOS */
  isMacOS: () => boolean;
  /** 判断当前宿主是否为 Windows */
  isWindows: () => boolean;
  /** 使用系统默认浏览器打开外部超链接 */
  openExternal: (url: string) => Promise<boolean>;
  /** 唤起系统原生目录选择器（非桌面环境优雅返回 null） */
  openDirectoryPicker: (options?: DirectoryPickerOptions) => Promise<string | null>;
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
    if (!this.isDesktop()) {
      return false;
    }
    return detectDesktopPlatform() === 'macos';
  }

  public isWindows(): boolean {
    if (!this.isDesktop()) {
      return false;
    }
    return detectDesktopPlatform() === 'windows';
  }

  public async openExternal(url: string): Promise<boolean> {
    if (!url) {
      return false;
    }
    return await this.core.shell.openExternalUrl(url);
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
}

export const desktopBridge: DesktopBridgeInterface = new DesktopBridgeImpl();
