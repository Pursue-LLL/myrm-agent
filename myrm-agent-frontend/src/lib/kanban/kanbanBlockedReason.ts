/**
 * [INPUT]
 * - @shared/config/kanban_blocked_reasons.json (POS: 服务端自己拥有的阻塞原因原文，前后端共用，由服务端契约测试核对)
 *
 * [OUTPUT]
 * - blockedReasonText: 把服务端写入的任务阻塞原因译成界面语言；不认识的原因原样返回
 *
 * [POS]
 * 看板卡片、任务抽屉与任务 toast/系统通知显示阻塞原因的唯一入口。服务端的原因是英文句子或标记（频道命令、诊断、活动流等处原样展示），
 * 这里按整句匹配出界面语言的文案，文案 key 是 `blockedReason.<JSON key>`；缺文案由 `kanbanBlockedReason.test.ts` 拦下。
 * 原因的集合是开放的：目标模式的暂停原因、预算耗尽（含轮数）、智能体自己写的原因都不在表里，按设计原样显示。
 */
import blockedReasons from '@shared/config/kanban_blocked_reasons.json';

// A Map, not an object literal: the reason is server text, and `{}['constructor']` is a function.
const BLOCKED_REASON_KEYS: ReadonlyMap<string, string> = new Map(
  Object.entries(blockedReasons).map(([id, sentence]) => [sentence, `blockedReason.${id}`]),
);

/** `t` is the translator of the `kanban` namespace. */
export function blockedReasonText(reason: string, t: (key: string) => string): string {
  const key = BLOCKED_REASON_KEYS.get(reason);
  return key ? t(key) : reason;
}
