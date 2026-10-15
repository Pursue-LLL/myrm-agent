/**
 * 安静时刻「有更新可用」CTA 编排套件 - 核心计算引擎
 *
 * 纯函数实现安静时刻检测、快照 TTL 验证、版本退避判定与动作直达上下文二次校验。
 */

import type {
  QuietEvaluationResult,
  QuietMomentBlockReason,
  QuietMomentContext,
  UpdateAvailabilitySnapshot,
  DismissedVersionRecord,
  UpdateOfferEligibility,
} from './quietMomentUpdateTypes';

export const DEFAULT_TYPING_GRACE_MS = 5_000;
export const DEFAULT_FRESH_SNAPSHOT_TTL_MS = 60_000;
export const DEFAULT_EMPTY_SNAPSHOT_TTL_MS = 5_000;
export const DEFAULT_OFFER_COOLDOWN_MS = 14_400_000; // 4 小时冷却

/**
 * 判定应用当前是否处于真正的“安静时刻”
 * 满足条件：窗口可见且拥有焦点、用户无近期按键输入、无在途长任务/流式响应、无阻塞级模态弹窗或遮罩、无安装中任务
 */
export function evaluateAppQuietness(ctx: QuietMomentContext): QuietEvaluationResult {
  if (!ctx.isDocumentVisible || !ctx.isWindowFocused) {
    return {
      isQuiet: false,
      reason: 'window_not_visible_or_blurred',
    };
  }

  const elapsedSinceType = ctx.now - ctx.lastTypedAt;
  const gracePeriod = ctx.typingGraceMs > 0 ? ctx.typingGraceMs : DEFAULT_TYPING_GRACE_MS;
  if (elapsedSinceType >= 0 && elapsedSinceType < gracePeriod) {
    return {
      isQuiet: false,
      reason: 'user_actively_typing',
    };
  }

  if (ctx.hasActiveStreamingOrTask) {
    return {
      isQuiet: false,
      reason: 'active_task_or_streaming',
    };
  }

  if (ctx.hasBlockingSurface) {
    return {
      isQuiet: false,
      reason: 'blocking_surface_open',
    };
  }

  if (ctx.isInstallingBusy) {
    return {
      isQuiet: false,
      reason: 'install_busy',
    };
  }

  return {
    isQuiet: true,
  };
}

/**
 * 快照新鲜度判定：复用短期内获取的可用性状态，避免秒级轮询打爆后端
 */
export function isSnapshotFresh(
  snapshot: UpdateAvailabilitySnapshot | null,
  now: number,
  freshTtlMs: number = DEFAULT_FRESH_SNAPSHOT_TTL_MS,
  emptyTtlMs: number = DEFAULT_EMPTY_SNAPSHOT_TTL_MS,
): boolean {
  if (!snapshot) {
    return false;
  }
  const maxAge = snapshot.version ? freshTtlMs : emptyTtlMs;
  return now - snapshot.readAt <= maxAge;
}

/**
 * 检查目标版本是否处于用户忽略或推迟提醒列表中
 */
export function isVersionDismissed(
  version: string,
  records: DismissedVersionRecord[],
  now: number,
): boolean {
  if (!version) {
    return false;
  }
  const matched = records.find((rec) => {
    return rec.version === version;
  });
  if (!matched) {
    return false;
  }
  // 未指定 remindAfter 表示用户永久跳过该版本
  if (matched.remindAfter === undefined) {
    return true;
  }
  // 处于推迟提醒有效期内
  return now < matched.remindAfter;
}

export interface EligibilityEvaluationParams {
  ctx: QuietMomentContext;
  snapshot: UpdateAvailabilitySnapshot | null;
  dismissedRecords: DismissedVersionRecord[];
  lastOfferedAt?: number;
  cooldownMs?: number;
}

/**
 * 综合评估是否可以在当前安静时刻弹出有更新可用横幅
 */
export function evaluateUpdateOfferEligibility(
  params: EligibilityEvaluationParams,
): UpdateOfferEligibility {
  const { ctx, snapshot, dismissedRecords, lastOfferedAt, cooldownMs = DEFAULT_OFFER_COOLDOWN_MS } = params;

  if (ctx.connectionMode !== 'local' && ctx.connectionMode !== 'hybrid') {
    return {
      canOffer: false,
      blockReason: 'connection_mode_ineligible',
    };
  }

  const quietResult = evaluateAppQuietness(ctx);
  if (!quietResult.isQuiet) {
    return {
      canOffer: false,
      blockReason: quietResult.reason,
    };
  }

  if (!snapshot || !snapshot.version) {
    return {
      canOffer: false,
      blockReason: 'snapshot_expired_or_absent',
    };
  }

  if (isVersionDismissed(snapshot.version, dismissedRecords, ctx.now)) {
    return {
      canOffer: false,
      blockReason: 'version_already_dismissed',
    };
  }

  if (lastOfferedAt !== undefined && ctx.now - lastOfferedAt < cooldownMs) {
    return {
      canOffer: false,
      blockReason: 'cooling_down',
    };
  }

  return {
    canOffer: true,
    tipId: `update-offer:${snapshot.version}`,
  };
}

/**
 * 动作直达前置校验：在用户点击“立即更新/重启”瞬间做二次上下文验证
 * 确保环境世代未更迭且当前没有紧急全屏任务突发，防止出现错误安装副作用
 */
export function validateActionContext(
  expectedGeneration: number,
  currentGeneration: number,
  ctx: QuietMomentContext,
): boolean {
  if (expectedGeneration !== currentGeneration) {
    return false;
  }
  if (ctx.isInstallingBusy || ctx.hasActiveStreamingOrTask) {
    return false;
  }
  return true;
}

/**
 * 格式化文件下载大小，呈现可读性好的 MB 字符串
 */
export function formatDownloadSize(mb?: number): string {
  if (mb === undefined || mb <= 0) {
    return '';
  }
  if (mb >= 1024) {
    return `${(mb / 1024).toFixed(1)} GB`;
  }
  return `${mb.toFixed(1)} MB`;
}
