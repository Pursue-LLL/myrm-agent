/**
 * 系统配置类型定义
 *
 * 与 Rust 后端的 SystemConfig 结构保持一致
 */

export interface SystemConfig {
  /** 是否启用 WebUI 模式 */
  enableWebUIMode: boolean;

  /** 是否允许远程访问 */
  enableRemoteAccess: boolean;

  /** WebUI 前端服务端口（Next.js Server） */
  webuiPort: number;

  /** API 后端服务端口（Python FastAPI） */
  apiPort: number;

  /** 是否需要密码（远程访问时强制开启） */
  requirePassword: boolean;

  /** 启动时自动开启 WebUI 服务 */
  autoStartWebUI: boolean;

  /** 关闭窗口时隐藏到托盘（而不是直接退出） */
  closeToTray: boolean;

  /** 配置文件版本（用于未来迁移） */
  configVersion: number;

  /** 全局唤醒快捷键 */
  globalShortcut: string;

  /** Appshot 截屏快捷键 */
  appshotShortcut: string;

  /** Appshot 截屏隐私黑名单 */
  appshotExcludedApps: string[];

  /** 是否启用 Locked Use（Computer Use 锁屏操作能力） */
  lockedUseEnabled: boolean;
}

/** 默认系统配置 */
export const DEFAULT_SYSTEM_CONFIG: SystemConfig = {
  enableWebUIMode: false,
  enableRemoteAccess: false,
  webuiPort: 3000,
  apiPort: 25808,
  requirePassword: true,
  autoStartWebUI: true,
  closeToTray: true,
  configVersion: 1,
  globalShortcut: 'Option+Space',
  appshotShortcut: 'CommandOrControl+Shift+A',
  appshotExcludedApps: ['微信', 'WeChat', '1Password', 'Bitwarden', 'KeePassXC', 'LastPass'],
  lockedUseEnabled: false,
};

/** 当前运行模式 */
export type RunMode = 'desktop' | 'webui';
