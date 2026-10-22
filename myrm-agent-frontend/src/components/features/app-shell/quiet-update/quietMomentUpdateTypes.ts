/**
 * 安静时刻「有更新可用」CTA 编排套件 - 类型定义
 *
 * 对标 claw/hermes-agent local-runtime-update-offer.ts
 * 覆盖安静时刻判定、可用性快照 TTL 复用、按版本忽略与 busy 互斥契约。
 */

export type UpdateOfferStatus =
  | 'idle'
  | 'checking'
  | 'available'
  | 'downloading'
  | 'ready'
  | 'installing'
  | 'up-to-date'
  | 'error';

export type QuietMomentBlockReason =
  | 'window_not_visible_or_blurred'
  | 'user_actively_typing'
  | 'active_task_or_streaming'
  | 'blocking_surface_open'
  | 'version_already_dismissed'
  | 'install_busy'
  | 'connection_mode_ineligible'
  | 'snapshot_expired_or_absent'
  | 'cooling_down';

export type ConnectionMode = 'local' | 'cloud' | 'hybrid';

export interface QuietMomentContext {
  isWindowFocused: boolean;
  isDocumentVisible: boolean;
  lastTypedAt: number;
  typingGraceMs: number;
  hasActiveStreamingOrTask: boolean;
  hasBlockingSurface: boolean;
  connectionMode: ConnectionMode;
  isInstallingBusy: boolean;
  now: number;
}

export interface UpdateAvailabilitySnapshot {
  version: string;
  currentVersion?: string;
  releaseDate?: string;
  releaseNotes?: string;
  downloadSizeMb?: number;
  readAt: number;
  isCritical?: boolean;
}

export interface DismissedVersionRecord {
  version: string;
  dismissedAt: number;
  remindAfter?: number;
}

export interface QuietEvaluationResult {
  isQuiet: boolean;
  reason?: QuietMomentBlockReason;
}

export interface UpdateOfferEligibility {
  canOffer: boolean;
  tipId?: string;
  blockReason?: QuietMomentBlockReason;
}
