/**
 * [INPUT]
 * - @shared/config/kanban_blocked_reasons.json (POS: 服务端写入的阻塞原因句子，前后端共用，由服务端契约测试核对)
 *
 * [OUTPUT]
 * - blockedReasonText: 把服务端写入的任务阻塞原因译成界面语言；不认识的原因原样返回
 *
 * [POS]
 * 看板卡片与任务抽屉显示阻塞原因的唯一入口。服务端的原因是英文句子（频道命令、诊断、活动流等处原样展示），
 * 这里按整句匹配出界面语言的文案；句子取自 shared/config/kanban_blocked_reasons.json，与服务端常量的一致性由服务端契约测试保证。
 */
import blockedReasons from '@shared/config/kanban_blocked_reasons.json';

// A Map, not an object literal: the reason is server text, and `{}['constructor']` is a function.
const BLOCKED_REASON_KEYS: ReadonlyMap<string, string> = new Map([
  [blockedReasons.parentMergeFailed, 'blockedReason.parentMergeFailed'],
]);

/** `t` is the translator of the `kanban` namespace. */
export function blockedReasonText(reason: string, t: (key: string) => string): string {
  const key = BLOCKED_REASON_KEYS.get(reason);
  return key ? t(key) : reason;
}
