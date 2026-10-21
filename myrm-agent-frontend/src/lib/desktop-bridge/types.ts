/**
 * [INPUT]
 * - Official Tauri plugins (shell, dialog)
 * - Standard HTML5 Web APIs (window.open)
 *
 * [OUTPUT]
 * - IDesktopBridge: 统一桌面原生与 Web 降级契约
 * - IShellBridge, NativeOpenFileDialogOptions: 外链与原生文件选择子契约
 * - DesktopPlatform: 运行平台类型
 * - DesktopWindowControlsState: 视窗留白状态
 *
 * [POS]
 * 前端桌面端原生桥接抽象契约（SSOT）。抹平 WebUI、Tauri 桌面端与 Cloud 托管沙箱的环境差异。
 * 契约只收录有后端实现（官方插件或已注册 Rust 命令）的原生能力。
 */

export type DesktopPlatform = 'macos' | 'windows' | 'linux' | 'web';

export interface DesktopWindowControlsState {
  controlsInsetTop: number;
  controlsInsetLeft: number;
  platform: DesktopPlatform;
  isDesktop: boolean;
  isOverlayTitlebar: boolean;
}

export interface NativeOpenFileDialogOptions {
  title?: string;
  multiple?: boolean;
  directory?: boolean;
  defaultPath?: string;
  filters?: Array<{ name: string; extensions: string[] }>;
}

export interface IShellBridge {
  /**
   * Hands a URL to the system browser. Resolves true once the request has been issued, false when the URL is empty
   * or the runtime refuses or cannot issue it.
   */
  openExternalUrl(url: string): Promise<boolean>;
  openFileDialog(options?: NativeOpenFileDialogOptions): Promise<string | string[] | null>;
}

export interface IDesktopBridge {
  readonly isDesktop: boolean;
  readonly platform: DesktopPlatform;
  readonly shell: IShellBridge;
  getWindowControlsState(): DesktopWindowControlsState;
}
