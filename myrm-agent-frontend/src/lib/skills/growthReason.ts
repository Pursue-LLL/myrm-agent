/**
 * [INPUT] none (pure parsing of the `reason_code` a growth case carries)
 * [OUTPUT] parseHeldReason: why a growth case waits for the user, as a closed set of kinds
 *          parseApplyFailure: why applying an approved case failed, as a closed set of kinds
 * [POS] 成长卡片按原因码本地化「为何需要你审核」与「为何应用失败」的出口；服务端只下发稳定的原因码，不下发面向用户的英文备注，
 *       `risk:` 前缀的风险信号由 scanRiskText 解析，应用失败是否存在由 applyError 决定，失败原因由 parseApplyFailure 分类，
 *       parseHeldReason 只处理其余三类。词表之外一律返回 null（或 generic），界面不展示，也不暴露内部代码。
 */

export type HeldReason = { kind: 'similar'; names: string[] } | { kind: 'scanFailed' } | { kind: 'evolutionLocked' };

export type ApplyFailureKind = 'staleBase' | 'unloadable' | 'generic';

const SIMILAR_PREFIX = 'similar:';
const SCAN_FAILED = 'scan_failed';
const EVOLUTION_LOCKED = 'evolution_locked';
const STALE_BASE = 'stale_base';
const SKILL_MD_UNLOADABLE = 'skill_md_unloadable';

/** Skill names never contain commas (`SKILL_NAME_PATTERN`), so the list separator is unambiguous. */
export function parseHeldReason(reasonCode: string | null | undefined): HeldReason | null {
  if (!reasonCode) {
    return null;
  }
  if (reasonCode.startsWith(SIMILAR_PREFIX)) {
    const names = reasonCode
      .slice(SIMILAR_PREFIX.length)
      .split(',')
      .filter((name) => name.length > 0);
    return names.length > 0 ? { kind: 'similar', names } : null;
  }
  if (reasonCode === SCAN_FAILED) {
    return { kind: 'scanFailed' };
  }
  if (reasonCode === EVOLUTION_LOCKED) {
    return { kind: 'evolutionLocked' };
  }
  return null;
}

/** `staleBase`: the skill changed after the proposal was made, so only rejecting resolves it. `unloadable`: the proposed file is not a valid skill. */
export function parseApplyFailure(reasonCode: string | null | undefined): ApplyFailureKind {
  if (reasonCode === STALE_BASE) {
    return 'staleBase';
  }
  if (reasonCode === SKILL_MD_UNLOADABLE) {
    return 'unloadable';
  }
  return 'generic';
}
