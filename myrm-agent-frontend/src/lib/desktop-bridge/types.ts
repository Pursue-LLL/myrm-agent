/**
 * [INPUT]
 * - Tauri IPC commands & events (__TAURI__)
 * - Standard HTML5 Web APIs (window.open, Notification, etc.)
 *
 * [OUTPUT]
 * - IDesktopBridge: 统一桌面原生与 Web 降级契约
 * - WindowMetrics: 视窗度量（交通灯、拖拽区）
 * - TrayStatusPayload: 托盘状态负载
 *
 * [POS]
 * 前端桌面端原生桥接抽象契约。抹平 WebUI、Tauri 桌面端与 Cloud 托管沙箱的环境差异。
 */

import type { LivenessState } from '@/hooks/shell/useLivenessState';

export interface UsageSummary {
  tokens: number;
  costUsd: number;
}

export interface WindowMetrics {
  isBorderless: boolean;
  trafficLightsPadding: number;
  titlebarHeight: number;
  dragRegionEnabled: boolean;
}

export interface TrayStatusPayload {
  liveness: LivenessState;
  activeTasksCount: number;
  usageSummary?: UsageSummary | null;
  tooltipText?: string;
}

export interface NativeNotificationPayload {
  title: string;
  body: string;
  kind?: 'info' | 'success' | 'warning' | 'error';
  sound?: boolean;
}

export interface IWindowBridge {
  getMetrics(): Promise<WindowMetrics>;
  minimize(): Promise<void>;
  maximize(): Promise<void>;
  toggleMaximize(): Promise<void>;
  close(): Promise<void>;
  isMaximized(): Promise<boolean>;
  startDragging(): Promise<void>;
}

export interface ITrayBridge {
  updateStatus(status: TrayStatusPayload): Promise<void>;
  onTrayEvent(handler: (event: { type: string; payload?: unknown }) => void): () => void;
}

export interface IShellBridge {
  openLocalFolder(path: string): Promise<boolean>;
  showInFileManager(path: string): Promise<boolean>;
  openExternalUrl(url: string): Promise<boolean>;
}

export interface IPowerBridge {
  acquireLock(reason: string): Promise<string | null>;
  releaseLock(lockId: string): Promise<boolean>;
}

export interface IAppshotBridge {
  listenAppshot(handler: (payload: { path: string; mimeType: string }) => void): () => void;
  captureScreen(): Promise<{ base64: string; mimeType: string } | null>;
}

export interface INotificationBridge {
  show(payload: NativeNotificationPayload): Promise<boolean>;
}

export interface IDesktopBridge {
  readonly isDesktop: boolean;
  readonly platform: 'macos' | 'windows' | 'linux' | 'web';
  readonly window: IWindowBridge;
  readonly tray: ITrayBridge;
  readonly shell: IShellBridge;
  readonly power: IPowerBridge;
  readonly appshot: IAppshotBridge;
  readonly notification: INotificationBridge;
}
